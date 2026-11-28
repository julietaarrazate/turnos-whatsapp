"""push (avisos al teléfono: dispositivos suscriptos y claves VAPID)

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-26 21:00:00

Expand: tablas nuevas, globales (como las sesiones y las llaves de acceso). Bajar la migración
borra los dispositivos suscriptos: cada persona vuelve a activar los avisos.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from migrations.rls import grant_crud

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "push_subscriptions",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("endpoint", sa.String(length=1000), nullable=False),
        sa.Column("p256dh", sa.String(length=200), nullable=False),
        sa.Column("auth", sa.String(length=100), nullable=False),
        sa.Column("user_agent", sa.String(length=400), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_push_subscriptions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_push_subscriptions")),
        sa.UniqueConstraint("endpoint", name=op.f("uq_push_subscriptions_endpoint")),
    )
    op.create_index(op.f("ix_push_subscriptions_user_id"), "push_subscriptions", ["user_id"])
    op.create_table(
        "push_keys",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("private_pem", sa.Text(), nullable=False),
        sa.Column("public_key", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_push_keys")),
    )
    grant_crud("push_subscriptions")
    op.execute("GRANT SELECT, INSERT ON push_keys TO app_runtime")


def downgrade() -> None:
    op.drop_table("push_keys")
    op.drop_index(op.f("ix_push_subscriptions_user_id"), table_name="push_subscriptions")
    op.drop_table("push_subscriptions")
