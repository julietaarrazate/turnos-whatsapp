"""passkeys (entrar con huella, cara o el bloqueo del teléfono)

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-26 06:00:00

Expand: tablas nuevas, globales del usuario (como auth_sessions). Bajar la migración solo
borra las llaves: cada persona vuelve a entrar con mail y contraseña.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from migrations.rls import grant_crud

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "passkeys",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("credential_id", sa.LargeBinary(), nullable=False),
        sa.Column("public_key", sa.LargeBinary(), nullable=False),
        sa.Column("sign_count", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_passkeys_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_passkeys")),
        sa.UniqueConstraint("credential_id", name=op.f("uq_passkeys_credential_id")),
    )
    op.create_index(op.f("ix_passkeys_user_id"), "passkeys", ["user_id"])
    op.create_table(
        "webauthn_challenges",
        sa.Column("challenge_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("purpose", sa.String(length=10), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "purpose IN ('REGISTER', 'LOGIN')", name=op.f("ck_webauthn_challenges_purpose")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_webauthn_challenges_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_webauthn_challenges")),
        sa.UniqueConstraint("challenge_hash", name=op.f("uq_webauthn_challenges_challenge_hash")),
    )
    grant_crud("passkeys")
    grant_crud("webauthn_challenges")


def downgrade() -> None:
    op.drop_table("webauthn_challenges")
    op.drop_index(op.f("ix_passkeys_user_id"), table_name="passkeys")
    op.drop_table("passkeys")
