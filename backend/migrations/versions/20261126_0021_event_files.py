"""event files (la pestaña Archivos: archivos y links del evento, por categoría)

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-26 04:30:00

Expand: tabla nueva y EVENT_FILE en documents.kind. El downgrade falla si ya hay documentos
EVENT_FILE (no se pierden archivos en silencio).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from migrations.rls import enable_tenant_rls, grant_crud

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KINDS_OLD = "kind IN ('RECEIPT', 'PURCHASE_ORDER', 'PROGRESS_PHOTO', 'PIECE_PLAN', 'VOICE_NOTE')"
_KINDS_NEW = (
    "kind IN ('RECEIPT', 'PURCHASE_ORDER', 'PROGRESS_PHOTO', 'PIECE_PLAN', 'VOICE_NOTE', "
    "'EVENT_FILE')"
)


def _kinds(check: str) -> None:
    op.drop_constraint(op.f("ck_documents_kind"), "documents", type_="check")
    op.create_check_constraint(op.f("ck_documents_kind"), "documents", check)


def upgrade() -> None:
    _kinds(_KINDS_NEW)
    op.create_table(
        "event_files",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("piece_id", sa.Uuid(), nullable=True),
        sa.Column("category", sa.String(length=10), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("url", sa.String(length=1000), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "category IN ('CLIENT', 'DESIGN', 'ADMIN', 'OTHER')",
            name=op.f("ck_event_files_category"),
        ),
        sa.CheckConstraint(
            "(document_id IS NULL) <> (url IS NULL)", name=op.f("ck_event_files_file_or_link")
        ),
        sa.CheckConstraint(
            "url IS NULL OR url LIKE 'https://%'", name=op.f("ck_event_files_https_only")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_event_files_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "event_id"],
            ["events.organization_id", "events.id"],
            name=op.f("fk_event_files_organization_id_event_id_events"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "piece_id"],
            ["event_pieces.organization_id", "event_pieces.id"],
            name=op.f("fk_event_files_organization_id_piece_id_event_pieces"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "document_id"],
            ["documents.organization_id", "documents.id"],
            name=op.f("fk_event_files_organization_id_document_id_documents"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_event_files_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_files")),
        sa.UniqueConstraint(
            "organization_id", "id", name=op.f("uq_event_files_organization_id_id")
        ),
    )
    op.create_index("ix_event_files_event_created", "event_files", ["event_id", "created_at"])
    grant_crud("event_files")
    enable_tenant_rls("event_files")


def downgrade() -> None:
    op.drop_index("ix_event_files_event_created", table_name="event_files")
    op.drop_table("event_files")
    _kinds(_KINDS_OLD)
