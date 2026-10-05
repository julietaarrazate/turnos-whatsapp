"""identity: organizations, users, memberships + funciones de contexto RLS

Revision ID: 0001
Revises:
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from migrations.rls import RUNTIME_ROLE, enable_tenant_rls, grant_crud
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column[object]]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    # Contexto de sesión leído por las políticas. Vacío o ausente => NULL => no hay filas.
    op.execute(
        "CREATE FUNCTION app_current_org() RETURNS uuid LANGUAGE sql STABLE AS "
        "$$ SELECT NULLIF(current_setting('app.org_id', true), '')::uuid $$"
    )
    op.execute(
        "CREATE FUNCTION app_current_user() RETURNS uuid LANGUAGE sql STABLE AS "
        "$$ SELECT NULLIF(current_setting('app.user_id', true), '')::uuid $$"
    )
    op.execute(f"GRANT USAGE ON SCHEMA public TO {RUNTIME_ROLE}")
    op.execute(f"GRANT EXECUTE ON FUNCTION app_current_org(), app_current_user() TO {RUNTIME_ROLE}")

    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("legal_name", sa.String(length=200), nullable=True),
        sa.Column("tax_id", sa.String(length=20), nullable=True),
        sa.Column("tax_condition", sa.String(length=20), nullable=False),
        sa.Column("base_currency", sa.String(length=3), server_default="ARS", nullable=False),
        sa.Column(
            "timezone",
            sa.String(length=64),
            server_default="America/Argentina/Buenos_Aires",
            nullable=False,
        ),
        sa.Column(
            "settings", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        *_timestamps(),
        sa.CheckConstraint(
            "tax_condition IN ('RI', 'MONOTRIBUTO', 'EXENTO')",
            name=op.f("ck_organizations_tax_condition"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organizations")),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index("uq_users_email_lower", "users", [sa.text("lower(email)")], unique=True)

    op.create_table(
        "memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "role IN ('OWNER', 'ADMIN', 'MANAGER', 'QUOTER', 'PRODUCTION', 'VIEWER')",
            name=op.f("ck_memberships_role"),
        ),
        sa.CheckConstraint(
            "status IN ('INVITED', 'ACTIVE', 'DISABLED')", name=op.f("ck_memberships_status")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_memberships_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_memberships_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_memberships")),
        sa.UniqueConstraint(
            "organization_id", "id", name=op.f("uq_memberships_organization_id_id")
        ),
        sa.UniqueConstraint(
            "organization_id", "user_id", name=op.f("uq_memberships_organization_id_user_id")
        ),
    )
    op.create_index(op.f("ix_memberships_user_id"), "memberships", ["user_id"], unique=False)

    for table in ("organizations", "users", "memberships"):
        grant_crud(table)

    # memberships: tenant estándar + cada usuario ve sus propias membresías (para elegir org al
    # iniciar sesión). Las escrituras quedan limitadas a la organización en contexto.
    enable_tenant_rls("memberships")
    op.execute(
        "CREATE POLICY own_memberships ON memberships FOR SELECT "
        "USING (user_id = app_current_user())"
    )

    # organizations: se lee la org en contexto o aquellas donde el usuario tiene membresía activa.
    # Solo se escribe la organización en contexto.
    op.execute("ALTER TABLE organizations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE organizations FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY org_isolation ON organizations "
        "USING (id = app_current_org()) WITH CHECK (id = app_current_org())"
    )
    op.execute(
        "CREATE POLICY org_member_read ON organizations FOR SELECT USING ("
        " id IN (SELECT organization_id FROM memberships"
        "        WHERE user_id = app_current_user() AND status = 'ACTIVE'))"
    )


def downgrade() -> None:
    # La política de organizations referencia memberships: se borra primero.
    op.execute("DROP POLICY org_member_read ON organizations")
    op.drop_table("memberships")
    op.drop_index("uq_users_email_lower", table_name="users")
    op.drop_table("users")
    op.drop_table("organizations")
    op.execute("DROP FUNCTION app_current_user()")
    op.execute("DROP FUNCTION app_current_org()")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {RUNTIME_ROLE}")
