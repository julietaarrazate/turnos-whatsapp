"""crew role (taller / montaje)

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-26 02:00:00

Expand: el CHECK de rol de membresías e invitaciones acepta CREW. El downgrade falla si ya
hay alguien con ese rol (Postgres valida el CHECK nuevo contra todas las filas, sin RLS de
por medio): a propósito, porque convertirlo en otro rol en silencio le daría más acceso del
que tenía (cualquier otro rol ve presupuestos y clientes). Hay que cambiarle el rol antes.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD = "'OWNER', 'ADMIN', 'MANAGER', 'QUOTER', 'PRODUCTION', 'VIEWER'"
_NEW = _OLD + ", 'CREW'"
_TABLES = ("memberships", "invitations")


def _recreate(roles: str) -> None:
    for table in _TABLES:
        op.drop_constraint(op.f(f"ck_{table}_role"), table, type_="check")
        op.create_check_constraint(op.f(f"ck_{table}_role"), table, f"role IN ({roles})")


def upgrade() -> None:
    _recreate(_NEW)


def downgrade() -> None:
    _recreate(_OLD)
