"""piece updates (avances con foto) y documentos de tipo foto de avance

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-26 03:00:00

Expand: tabla nueva y un valor nuevo en el CHECK de ``documents.kind``. El runtime puede leer,
insertar y borrar avances: no hay endpoint de edición ni de borrado; el DELETE es para que borrar
una pieza o un evento arrastre sus avances (ON DELETE CASCADE).
El downgrade falla si ya hay documentos PROGRESS_PHOTO (el CHECK viejo no los acepta y los
documentos son inmutables): a propósito, para no perder fotos en silencio.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from migrations.rls import enable_tenant_rls

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KINDS_OLD = "kind IN ('RECEIPT', 'PURCHASE_ORDER')"
_KINDS_NEW = "kind IN ('RECEIPT', 'PURCHASE_ORDER', 'PROGRESS_PHOTO')"


def _kinds(check: str) -> None:
    op.drop_constraint(op.f("ck_documents_kind"), "documents", type_="check")
    op.create_check_constraint(op.f("ck_documents_kind"), "documents", check)


def upgrade() -> None:
    _kinds(_KINDS_NEW)
    op.create_table(
        "piece_updates",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("piece_id", sa.Uuid(), nullable=False),
        sa.Column("author_user_id", sa.Uuid(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("photo_document_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "note IS NOT NULL OR photo_document_id IS NOT NULL",
            name=op.f("ck_piece_updates_has_content"),
        ),
        sa.ForeignKeyConstraint(
            ["author_user_id"], ["users.id"], name=op.f("fk_piece_updates_author_user_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "piece_id"],
            ["event_pieces.organization_id", "event_pieces.id"],
            name=op.f("fk_piece_updates_organization_id_piece_id_event_pieces"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "event_id"],
            ["events.organization_id", "events.id"],
            name=op.f("fk_piece_updates_organization_id_event_id_events"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "photo_document_id"],
            ["documents.organization_id", "documents.id"],
            name=op.f("fk_piece_updates_organization_id_photo_document_id_documents"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_piece_updates_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_piece_updates")),
        sa.UniqueConstraint(
            "organization_id", "id", name=op.f("uq_piece_updates_organization_id_id")
        ),
    )
    op.create_index("ix_piece_updates_piece_created", "piece_updates", ["piece_id", "created_at"])
    op.create_index("ix_piece_updates_event_created", "piece_updates", ["event_id", "created_at"])
    op.execute("GRANT SELECT, INSERT, DELETE ON piece_updates TO app_runtime")
    enable_tenant_rls("piece_updates")


def downgrade() -> None:
    op.drop_index("ix_piece_updates_event_created", table_name="piece_updates")
    op.drop_index("ix_piece_updates_piece_created", table_name="piece_updates")
    op.drop_table("piece_updates")
    _kinds(_KINDS_OLD)
