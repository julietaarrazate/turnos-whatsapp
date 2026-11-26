"""expected files (la lista de archivos que el evento tiene que tener)

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-26 05:00:00

Expand: tabla nueva. Bajar la migración solo pierde la lista (no archivos).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from migrations.rls import enable_tenant_rls, grant_crud

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "event_expected_files",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("category", sa.String(length=10), nullable=False),
        sa.Column("sort", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "category IN ('CLIENT', 'DESIGN', 'ADMIN', 'OTHER')",
            name=op.f("ck_event_expected_files_category"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "event_id"],
            ["events.organization_id", "events.id"],
            name=op.f("fk_event_expected_files_organization_id_event_id_events"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_event_expected_files_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_expected_files")),
        sa.UniqueConstraint(
            "organization_id", "id", name=op.f("uq_event_expected_files_organization_id_id")
        ),
        sa.UniqueConstraint(
            "event_id", "title", name=op.f("uq_event_expected_files_event_id_title")
        ),
    )
    op.create_index(op.f("ix_event_expected_files_event_id"), "event_expected_files", ["event_id"])
    grant_crud("event_expected_files")
    enable_tenant_rls("event_expected_files")


def downgrade() -> None:
    op.drop_index(op.f("ix_event_expected_files_event_id"), table_name="event_expected_files")
    op.drop_table("event_expected_files")
