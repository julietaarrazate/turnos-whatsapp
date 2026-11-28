"""platform admin: organizaciones pausables y lectura de la lista para la dueña de la plataforma

Revision ID: 0028
Revises: 0027
Create Date: 2026-11-28 03:00:00

Expand: una columna nueva con NULL (nadie queda pausado) y una política de solo lectura sobre
``organizations`` que se activa únicamente con ``app.platform_admin = 'on'`` (lo fija el panel de
administración después de verificar el email contra PLATFORM_ADMINS). Los datos de cada
organización se siguen leyendo con su propio contexto de tenant.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "CREATE POLICY platform_admin_read ON organizations FOR SELECT "
        "USING (current_setting('app.platform_admin', true) = 'on')"
    )


def downgrade() -> None:
    op.execute("DROP POLICY platform_admin_read ON organizations")
    op.drop_column("organizations", "suspended_at")
