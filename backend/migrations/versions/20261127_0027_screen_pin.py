"""screen pin (bloqueo de pantalla con PIN)

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-27 12:00:00

Expand: dos columnas nuevas en users, con default. Bajar la migración saca el PIN de todos (la
app vuelve a no bloquearse).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("pin_hash", sa.String(length=255), nullable=True))
    op.add_column(
        "users",
        sa.Column("pin_failures", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("users", "pin_failures")
    op.drop_column("users", "pin_hash")
