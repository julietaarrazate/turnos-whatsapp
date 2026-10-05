"""Acceso a datos: engine, sesiones con contexto de tenant y base declarativa."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import Depends
from sqlalchemy import (
    Connection,
    DateTime,
    Engine,
    MetaData,
    UniqueConstraint,
    create_engine,
    event,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, SessionTransaction, mapped_column
from sqlalchemy.orm import sessionmaker as _sessionmaker

from app.core.config import get_settings
from app.core.ids import uuid7

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {datetime: DateTime(timezone=True)}  # noqa: RUF012


class IdMixin:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


def tenant_unique() -> UniqueConstraint:
    """``UNIQUE (organization_id, id)``: destino de las FK compuestas entre tablas tenant."""
    return UniqueConstraint("organization_id", "id")


@dataclass(frozen=True)
class DbContext:
    """Variables de sesión que leen las políticas RLS (``app_current_org()``, etc.)."""

    organization_id: UUID | None = None
    user_id: UUID | None = None
    # Hash de un token público (invitación, propuesta): capacidad para leer esa fila puntual.
    token_hash: str | None = None


_CONTEXT_KEY = "db_context"


def _apply_context(connection: Connection, ctx: DbContext) -> None:
    connection.execute(
        text(
            "SELECT set_config('app.org_id', :org, true), set_config('app.user_id', :usr, true),"
            " set_config('app.token_hash', :tok, true)"
        ),
        {
            "org": str(ctx.organization_id) if ctx.organization_id else "",
            "usr": str(ctx.user_id) if ctx.user_id else "",
            "tok": ctx.token_hash or "",
        },
    )


def set_context(session: Session, ctx: DbContext) -> None:
    """Fija el contexto de tenant para esta sesión.

    Se aplica a la transacción en curso y se re-aplica automáticamente al comenzar cada
    transacción nueva (``set_config(..., true)`` es local a la transacción, lo que lo hace
    compatible con PgBouncer en modo transacción).
    """
    session.info[_CONTEXT_KEY] = ctx
    if session.in_transaction():
        _apply_context(session.connection(), ctx)


class AppSession(Session):
    pass


@event.listens_for(AppSession, "after_begin")
def _on_begin(session: Session, _tx: SessionTransaction, connection: Connection) -> None:
    ctx = session.info.get(_CONTEXT_KEY)
    if isinstance(ctx, DbContext):
        _apply_context(connection, ctx)


@lru_cache
def get_engine() -> Engine:
    return create_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def get_sessionmaker() -> _sessionmaker[AppSession]:
    return _sessionmaker(bind=get_engine(), class_=AppSession, expire_on_commit=False)


@contextmanager
def session_scope(ctx: DbContext | None = None) -> Iterator[AppSession]:
    """Una transacción: commit al salir, rollback si hay excepción."""
    session = get_sessionmaker()()
    if ctx is not None:
        session.info[_CONTEXT_KEY] = ctx
    try:
        with session.begin():
            yield session
    finally:
        session.close()


def get_db() -> Iterator[AppSession]:
    """Una transacción por request.

    Se usa con ``scope="function"``: el commit ocurre ANTES de enviar la respuesta. Con el
    scope por defecto, un commit fallido igual devolvería 200 (verificado en FastAPI 0.142).
    """
    session = get_sessionmaker()()
    try:
        with session.begin():
            yield session
    finally:
        session.close()


DbSession = Annotated[AppSession, Depends(get_db, scope="function")]
