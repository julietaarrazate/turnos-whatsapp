"""Datos de prueba. Escriben con el rol de runtime y el contexto correcto (como la app)."""

from dataclasses import dataclass
from uuid import UUID

from app.core.db import DbContext, session_scope
from app.core.enums import Role
from app.core.ids import uuid7
from app.core.security import hash_password
from app.modules.identity import Membership, Organization, User
from app.modules.organizations import provision_organization

DEFAULT_PASSWORD = "contraseña-segura-123"
_DEFAULT_HASH = hash_password(DEFAULT_PASSWORD)  # argon2 es lento a propósito: se calcula una vez


@dataclass(frozen=True)
class Member:
    user_id: UUID
    email: str
    organization_id: UUID
    membership_id: UUID
    role: Role
    password: str = DEFAULT_PASSWORD


def create_org(name: str = "Productora", **fields: object) -> UUID:
    org_id = uuid7()
    with session_scope(DbContext(organization_id=org_id)) as s:
        s.add(Organization(id=org_id, name=name, **fields))
        s.flush()
        provision_organization(s, org_id)
    return org_id


def create_user(email: str, name: str = "Persona", password: str = DEFAULT_PASSWORD) -> UUID:
    user_id = uuid7()
    with session_scope() as s:
        password_hash = _DEFAULT_HASH if password == DEFAULT_PASSWORD else hash_password(password)
        s.add(User(id=user_id, email=email, name=name, password_hash=password_hash))
    return user_id


def add_member(
    org_id: UUID, user_id: UUID, email: str, role: Role = Role.OWNER, status: str = "ACTIVE"
) -> Member:
    membership_id = uuid7()
    with session_scope(DbContext(organization_id=org_id)) as s:
        s.add(
            Membership(
                id=membership_id,
                organization_id=org_id,
                user_id=user_id,
                role=role.value,
                status=status,
            )
        )
    return Member(user_id, email, org_id, membership_id, role)


def create_member(
    email: str = "owner@example.com", role: Role = Role.OWNER, org_id: UUID | None = None
) -> Member:
    org_id = org_id or create_org()
    user_id = create_user(email)
    return add_member(org_id, user_id, email, role)
