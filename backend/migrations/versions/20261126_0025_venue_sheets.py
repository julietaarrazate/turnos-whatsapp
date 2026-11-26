"""venue sheets (ficha reutilizable de cada lugar)

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-26 20:00:00

Expand: tabla nueva con RLS de organización. Bajar la migración borra las fichas (los eventos
conservan el nombre del lugar).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from migrations.rls import enable_tenant_rls, grant_crud

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "venue_sheets",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("name_key", sa.String(length=200), nullable=False),
        sa.Column("address", sa.String(length=300), nullable=True),
        sa.Column("maps_url", sa.String(length=1000), nullable=True),
        sa.Column("load_in", sa.Text(), nullable=True),
        sa.Column("measures", sa.Text(), nullable=True),
        sa.Column("rules", sa.Text(), nullable=True),
        sa.Column("contacts", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "maps_url IS NULL OR maps_url LIKE 'https://%'", name=op.f("ck_venue_sheets_https_only")
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["users.id"], name=op.f("fk_venue_sheets_updated_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_venue_sheets_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_venue_sheets")),
        sa.UniqueConstraint(
            "organization_id", "id", name=op.f("uq_venue_sheets_organization_id_id")
        ),
        sa.UniqueConstraint(
            "organization_id", "name_key", name=op.f("uq_venue_sheets_organization_id_name_key")
        ),
    )
    grant_crud("venue_sheets")
    enable_tenant_rls("venue_sheets")


def downgrade() -> None:
    op.drop_table("venue_sheets")
