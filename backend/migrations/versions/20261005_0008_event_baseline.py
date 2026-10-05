"""event baseline: versión aceptada del evento y método de aprobación

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-05 23:21:33.026113
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Expand: columna nullable, sin backfill (ningún evento fue aprobado todavía).
    op.add_column("events", sa.Column("accepted_budget_version_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_events_accepted_budget_version",
        "events",
        "budget_versions",
        ["organization_id", "accepted_budget_version_id"],
        ["organization_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "approval_method", "proposals", "approval_method IN ('ONLINE', 'MANUAL')"
    )


def downgrade() -> None:
    op.drop_constraint("approval_method", "proposals", type_="check")
    op.drop_constraint("fk_events_accepted_budget_version", "events", type_="foreignkey")
    op.drop_column("events", "accepted_budget_version_id")
