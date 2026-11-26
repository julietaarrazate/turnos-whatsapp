"""piece plans (planos por pieza, con versiones)

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-26 03:30:00

Expand: tabla nueva y un valor nuevo en el CHECK de ``documents.kind``. Los planos no se editan
ni se borran desde la app (DELETE solo para el ON DELETE CASCADE de pieza y evento).
El downgrade falla si ya hay documentos PIECE_PLAN: a propósito, para no perder planos.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from migrations.rls import enable_tenant_rls

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KINDS_OLD = "kind IN ('RECEIPT', 'PURCHASE_ORDER', 'PROGRESS_PHOTO')"
_KINDS_NEW = "kind IN ('RECEIPT', 'PURCHASE_ORDER', 'PROGRESS_PHOTO', 'PIECE_PLAN')"


def _kinds(check: str) -> None:
    op.drop_constraint(op.f("ck_documents_kind"), "documents", type_="check")
    op.create_check_constraint(op.f("ck_documents_kind"), "documents", check)


def upgrade() -> None:
    _kinds(_KINDS_NEW)
    op.create_table(
        "piece_plans",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("piece_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("uploaded_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("version >= 1", name=op.f("ck_piece_plans_version_positive")),
        sa.ForeignKeyConstraint(
            ["uploaded_by"], ["users.id"], name=op.f("fk_piece_plans_uploaded_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "piece_id"],
            ["event_pieces.organization_id", "event_pieces.id"],
            name=op.f("fk_piece_plans_organization_id_piece_id_event_pieces"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "event_id"],
            ["events.organization_id", "events.id"],
            name=op.f("fk_piece_plans_organization_id_event_id_events"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "document_id"],
            ["documents.organization_id", "documents.id"],
            name=op.f("fk_piece_plans_organization_id_document_id_documents"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_piece_plans_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_piece_plans")),
        sa.UniqueConstraint(
            "organization_id", "id", name=op.f("uq_piece_plans_organization_id_id")
        ),
        sa.UniqueConstraint(
            "piece_id", "title", "version", name=op.f("uq_piece_plans_piece_id_title_version")
        ),
    )
    op.create_index(op.f("ix_piece_plans_piece_id"), "piece_plans", ["piece_id"], unique=False)
    op.execute("GRANT SELECT, INSERT, DELETE ON piece_plans TO app_runtime")
    enable_tenant_rls("piece_plans")


def downgrade() -> None:
    op.drop_index(op.f("ix_piece_plans_piece_id"), table_name="piece_plans")
    op.drop_table("piece_plans")
    _kinds(_KINDS_OLD)
