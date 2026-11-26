"""file approvals (el cliente aprueba un diseño por link, sin cuenta)

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-26 12:00:00

Expand: tabla nueva con RLS de organización y, como las propuestas, lectura por el hash del token
(el cliente presenta el link y con eso se averigua la organización). Bajar la migración borra los
pedidos de aprobación (los archivos quedan).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from migrations.rls import enable_tenant_rls, grant_crud

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "file_approvals",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("file_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by_name", sa.String(length=120), nullable=True),
        sa.Column("comment", sa.String(length=1000), nullable=True),
        sa.Column("decision_ip", sa.String(length=64), nullable=True),
        sa.Column("decision_user_agent", sa.String(length=400), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'CHANGES', 'REPLACED')",
            name=op.f("ck_file_approvals_status"),
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"], ["users.id"], name=op.f("fk_file_approvals_requested_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "event_id"],
            ["events.organization_id", "events.id"],
            name=op.f("fk_file_approvals_organization_id_event_id_events"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "file_id"],
            ["event_files.organization_id", "event_files.id"],
            name=op.f("fk_file_approvals_organization_id_file_id_event_files"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_file_approvals_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_file_approvals")),
        sa.UniqueConstraint(
            "organization_id", "id", name=op.f("uq_file_approvals_organization_id_id")
        ),
        sa.UniqueConstraint("token_hash", name=op.f("uq_file_approvals_token_hash")),
    )
    op.create_index("ix_file_approvals_file_created", "file_approvals", ["file_id", "created_at"])
    grant_crud("file_approvals")
    enable_tenant_rls("file_approvals")
    # El cliente (sin sesión) puede leer SOLO el pedido cuyo token presenta (como proposals).
    op.execute(
        "CREATE POLICY file_approval_by_token ON file_approvals FOR SELECT "
        "USING (token_hash = NULLIF(current_setting('app.token_hash', true), ''))"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS file_approval_by_token ON file_approvals")
    op.drop_index("ix_file_approvals_file_created", table_name="file_approvals")
    op.drop_table("file_approvals")
