from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError

from app.core.db import AppSession
from app.core.errors import AppError, not_found
from app.core.security import utcnow
from app.modules.audit import diff, record
from app.modules.auth import TenantContext
from app.modules.clients.models import Client, ClientContact
from app.modules.clients.schemas import (
    ClientIn,
    ClientOut,
    ClientPage,
    ClientSummary,
    ClientUpdate,
    ContactIn,
    ContactOut,
)

_FIELDS = ("name", "legal_name", "tax_id", "tax_condition", "address", "city", "notes")


def _audit(
    db: AppSession, ctx: TenantContext, action: str, client_id: UUID, **changes: Any
) -> None:
    record(
        db,
        organization_id=ctx.organization_id,
        action=action,
        entity_type="client",
        entity_id=client_id,
        actor_user_id=ctx.user_id,
        ip=ctx.client.ip,
        user_agent=ctx.client.user_agent,
        **changes,
    )


def _get(db: AppSession, ctx: TenantContext, client_id: UUID) -> Client:
    client = db.execute(
        select(Client).where(
            Client.id == client_id,
            Client.organization_id == ctx.organization_id,
            Client.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if client is None:
        raise not_found()
    return client


def _contacts(db: AppSession, client_id: UUID) -> list[ClientContact]:
    return list(
        db.execute(
            select(ClientContact)
            .where(ClientContact.client_id == client_id)
            .order_by(ClientContact.is_primary.desc(), ClientContact.name)
        ).scalars()
    )


def _out(db: AppSession, client: Client) -> ClientOut:
    return ClientOut(
        id=client.id,
        name=client.name,
        legal_name=client.legal_name,
        tax_id=client.tax_id,
        tax_condition=client.tax_condition,
        address=client.address,
        city=client.city,
        notes=client.notes,
        contacts=[
            ContactOut(
                id=c.id,
                name=c.name,
                position=c.position,
                email=c.email,
                phone=c.phone,
                is_primary=c.is_primary,
            )
            for c in _contacts(db, client.id)
        ],
    )


def _snapshot(client: Client) -> dict[str, Any]:
    return {field: getattr(client, field) for field in _FIELDS}


def _replace_contacts(
    db: AppSession, ctx: TenantContext, client_id: UUID, contacts: list[ContactIn]
) -> None:
    db.execute(delete(ClientContact).where(ClientContact.client_id == client_id))
    primary_seen = False
    for contact in contacts:
        is_primary = contact.is_primary and not primary_seen
        primary_seen = primary_seen or is_primary
        db.add(
            ClientContact(
                organization_id=ctx.organization_id,
                client_id=client_id,
                name=contact.name.strip(),
                position=contact.position,
                email=str(contact.email).lower() if contact.email else None,
                phone=contact.phone,
                is_primary=is_primary,
            )
        )


def _flush_unique(db: AppSession) -> None:
    try:
        db.flush()
    except IntegrityError as exc:
        if "uq_clients_org_name" in str(exc.orig):
            raise AppError(409, "client_name_taken", "Ya existe un cliente con ese nombre") from exc
        raise


def list_clients(
    db: AppSession, ctx: TenantContext, q: str | None, cursor: str | None, limit: int
) -> ClientPage:
    primary = (
        select(ClientContact.name)
        .where(ClientContact.client_id == Client.id, ClientContact.is_primary.is_(True))
        .limit(1)
        .scalar_subquery()
    )
    query = select(Client, primary).where(
        Client.organization_id == ctx.organization_id, Client.deleted_at.is_(None)
    )
    if q and q.strip():
        pattern = f"%{q.strip().lower()}%"
        query = query.where(
            or_(
                func.lower(Client.name).like(pattern),
                func.lower(Client.legal_name).like(pattern),
                Client.tax_id.like(pattern),
            )
        )
    if cursor:
        query = query.where(func.lower(Client.name) > cursor)
    rows = db.execute(query.order_by(func.lower(Client.name)).limit(limit + 1)).all()
    items = [
        ClientSummary(
            id=c.id,
            name=c.name,
            legal_name=c.legal_name,
            tax_id=c.tax_id,
            city=c.city,
            primary_contact=contact,
        )
        for c, contact in rows[:limit]
    ]
    next_cursor = rows[limit - 1][0].name.lower() if len(rows) > limit else None
    return ClientPage(items=items, next_cursor=next_cursor)


def get_client(db: AppSession, ctx: TenantContext, client_id: UUID) -> ClientOut:
    return _out(db, _get(db, ctx, client_id))


def create_client(db: AppSession, ctx: TenantContext, body: ClientIn) -> ClientOut:
    data = body.model_dump(include=set(_FIELDS))
    data["name"] = data["name"].strip()
    client = Client(organization_id=ctx.organization_id, **data)
    db.add(client)
    _flush_unique(db)
    _replace_contacts(db, ctx, client.id, body.contacts)
    db.flush()
    _audit(db, ctx, "client.created", client.id, after=_snapshot(client))
    return _out(db, client)


def update_client(
    db: AppSession, ctx: TenantContext, client_id: UUID, body: ClientUpdate
) -> ClientOut:
    client = _get(db, ctx, client_id)
    before = _snapshot(client)
    for field in body.model_fields_set & set(_FIELDS):
        value = getattr(body, field)
        if field == "name":
            if value is None:
                raise AppError(422, "name_required", "El nombre es obligatorio")
            value = value.strip()
        setattr(client, field, value)
    _flush_unique(db)
    if body.contacts is not None:
        _replace_contacts(db, ctx, client.id, body.contacts)
        db.flush()
    old, new = diff(before, _snapshot(client))
    if new or body.contacts is not None:
        _audit(db, ctx, "client.updated", client.id, before=old, after=new)
    return _out(db, client)


def delete_client(db: AppSession, ctx: TenantContext, client_id: UUID) -> None:
    client = _get(db, ctx, client_id)
    client.deleted_at = utcnow()
    _audit(db, ctx, "client.deleted", client.id)
