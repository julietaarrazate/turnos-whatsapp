"""voice notes (notas de voz en los avances)

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-26 04:00:00

Expand: columna nueva (nullable) en piece_updates, su FK compuesta a documents, el CHECK de
contenido que ahora acepta solo audio, y VOICE_NOTE en documents.kind. El downgrade falla si ya
hay notas de voz (a propósito: no se pierden en silencio).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KINDS_OLD = "kind IN ('RECEIPT', 'PURCHASE_ORDER', 'PROGRESS_PHOTO', 'PIECE_PLAN')"
_KINDS_NEW = "kind IN ('RECEIPT', 'PURCHASE_ORDER', 'PROGRESS_PHOTO', 'PIECE_PLAN', 'VOICE_NOTE')"
_CONTENT_OLD = "note IS NOT NULL OR photo_document_id IS NOT NULL"
_CONTENT_NEW = "note IS NOT NULL OR photo_document_id IS NOT NULL OR audio_document_id IS NOT NULL"
_FK = "fk_piece_updates_organization_id_audio_document_id_documents"


def _check(table: str, name: str, condition: str) -> None:
    op.drop_constraint(op.f(name), table, type_="check")
    op.create_check_constraint(op.f(name), table, condition)


def upgrade() -> None:
    _check("documents", "ck_documents_kind", _KINDS_NEW)
    op.add_column("piece_updates", sa.Column("audio_document_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f(_FK),
        "piece_updates",
        "documents",
        ["organization_id", "audio_document_id"],
        ["organization_id", "id"],
        ondelete="RESTRICT",
    )
    _check("piece_updates", "ck_piece_updates_has_content", _CONTENT_NEW)


def downgrade() -> None:
    _check("piece_updates", "ck_piece_updates_has_content", _CONTENT_OLD)
    op.drop_constraint(op.f(_FK), "piece_updates", type_="foreignkey")
    op.drop_column("piece_updates", "audio_document_id")
    _check("documents", "ck_documents_kind", _KINDS_OLD)
