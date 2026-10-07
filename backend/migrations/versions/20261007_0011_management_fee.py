"""management fee

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-07 02:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Expand: columnas con default 0, así las versiones existentes (y las congeladas) no cambian.
    op.add_column(
        "budget_versions",
        sa.Column(
            "management_fee_rate",
            sa.Numeric(precision=9, scale=6),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "budget_versions",
        sa.Column(
            "management_fee",
            sa.Numeric(precision=18, scale=2),
            server_default="0",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "management_fee",
        "budget_versions",
        "management_fee_rate >= 0 AND management_fee_rate < 1",
    )


def downgrade() -> None:
    op.drop_constraint("management_fee", "budget_versions", type_="check")
    op.drop_column("budget_versions", "management_fee")
    op.drop_column("budget_versions", "management_fee_rate")
