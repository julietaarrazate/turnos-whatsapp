"""Numeración correlativa por organización (eventos, presupuestos)."""

from uuid import UUID

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import AppSession, Base


class OrgCounter(Base):
    __tablename__ = "org_counters"

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), primary_key=True
    )
    name: Mapped[str] = mapped_column(String(30), primary_key=True)
    value: Mapped[int]


def next_number(db: AppSession, organization_id: UUID, name: str) -> int:
    """Atómico (INSERT … ON CONFLICT DO UPDATE … RETURNING): dos altas simultáneas no
    pueden recibir el mismo número."""
    stmt = (
        insert(OrgCounter)
        .values(organization_id=organization_id, name=name, value=1)
        .on_conflict_do_update(
            index_elements=[OrgCounter.organization_id, OrgCounter.name],
            set_={"value": OrgCounter.value + 1},
        )
        .returning(OrgCounter.value)
    )
    return int(db.execute(stmt).scalar_one())
