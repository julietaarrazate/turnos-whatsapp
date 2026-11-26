"""activity reads (la campanita: hasta cuándo vio cada persona la Actividad)

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-26 04:10:00

Expand: tabla nueva, una fila por persona y organización. No hay datos que perder al bajar
(solo se vuelve a avisar lo de la última semana).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from migrations.rls import enable_tenant_rls, grant_crud

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "activity_reads",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_activity_reads_user_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_activity_reads_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_activity_reads")),
        sa.UniqueConstraint(
            "organization_id", "id", name=op.f("uq_activity_reads_organization_id_id")
        ),
        sa.UniqueConstraint(
            "organization_id", "user_id", name=op.f("uq_activity_reads_organization_id_user_id")
        ),
    )
    grant_crud("activity_reads")
    enable_tenant_rls("activity_reads")


def downgrade() -> None:
    op.drop_table("activity_reads")
