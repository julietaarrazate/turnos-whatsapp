"""Aislamiento multi-tenant a nivel base de datos (ARCHITECTURE §7.2)."""

from uuid import UUID

import pytest
from sqlalchemy import Engine, select, text
from sqlalchemy.exc import DBAPIError

from app.core.db import DbContext, get_sessionmaker, session_scope, set_context
from app.core.enums import Role
from app.core.ids import uuid7
from app.modules.organizations import Membership, Organization
from app.modules.users import User


def _create_org_with_member(name: str, email: str) -> tuple[UUID, UUID]:
    org_id, user_id = uuid7(), uuid7()
    with session_scope() as s:
        s.add(User(id=user_id, email=email, name=name))
    with session_scope(DbContext(organization_id=org_id)) as s:
        s.add(Organization(id=org_id, name=name))
        s.flush()
        s.add(Membership(organization_id=org_id, user_id=user_id, role=Role.OWNER.value))
    return org_id, user_id


def test_every_tenant_table_has_forced_rls_and_composite_key(migrator_engine: Engine) -> None:
    with migrator_engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
                       EXISTS (
                         SELECT 1 FROM pg_constraint k
                         WHERE k.conrelid = c.oid AND k.contype = 'u'
                           AND (SELECT array_agg(a.attname::text ORDER BY a.attname)
                                FROM pg_attribute a
                                WHERE a.attrelid = c.oid AND a.attnum = ANY(k.conkey))
                               = ARRAY['id', 'organization_id']
                       ) AS has_composite_key
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
                WHERE c.relkind = 'r'
                  AND EXISTS (SELECT 1 FROM pg_attribute a
                              WHERE a.attrelid = c.oid AND a.attname = 'organization_id'
                                AND NOT a.attisdropped)
                """
            )
        ).all()
    assert rows, "debería haber al menos una tabla tenant"
    for name, rls, forced, composite in rows:
        assert rls, f"{name}: falta ENABLE ROW LEVEL SECURITY"
        assert forced, f"{name}: falta FORCE ROW LEVEL SECURITY"
        assert composite, f"{name}: falta UNIQUE (organization_id, id) para FK compuestas"


def test_runtime_role_cannot_bypass_rls(migrator_engine: Engine) -> None:
    with migrator_engine.connect() as conn:
        superuser, bypass = conn.execute(
            text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'app_runtime'")
        ).one()
        owners = conn.execute(
            text("SELECT DISTINCT tableowner FROM pg_tables WHERE schemaname = 'public'")
        ).scalars()
        assert "app_runtime" not in set(owners)
    assert not superuser
    assert not bypass


def test_without_context_no_rows_are_visible() -> None:
    _create_org_with_member("A", "a@example.com")
    with session_scope() as s:
        assert s.execute(select(Membership)).all() == []
        assert s.execute(select(Organization)).all() == []


def test_org_context_only_sees_own_rows() -> None:
    org_a, _ = _create_org_with_member("A", "a@example.com")
    org_b, _ = _create_org_with_member("B", "b@example.com")
    with session_scope(DbContext(organization_id=org_a)) as s:
        orgs = s.execute(select(Organization.id)).scalars().all()
        memberships = s.execute(select(Membership.organization_id)).scalars().all()
    assert orgs == [org_a]
    assert memberships == [org_a]
    assert org_b not in orgs


def test_cannot_write_rows_of_another_org() -> None:
    org_a, user_a = _create_org_with_member("A", "a@example.com")
    org_b, _ = _create_org_with_member("B", "b@example.com")
    with session_scope(DbContext(organization_id=org_a)) as s:
        s.add(Membership(organization_id=org_b, user_id=user_a, role=Role.VIEWER.value))
        with pytest.raises(DBAPIError, match="row-level security"):
            s.flush()
        s.rollback()


def test_cannot_update_another_org() -> None:
    org_a, _ = _create_org_with_member("A", "a@example.com")
    org_b, _ = _create_org_with_member("B", "b@example.com")
    with session_scope(DbContext(organization_id=org_a)) as s:
        result = s.execute(
            text("UPDATE organizations SET name = 'hack' WHERE id = :id"), {"id": org_b}
        )
        assert result.rowcount == 0  # type: ignore[attr-defined]


def test_user_sees_own_memberships_across_orgs_without_org_context() -> None:
    org_a, user = _create_org_with_member("A", "multi@example.com")
    org_b = uuid7()
    with session_scope(DbContext(organization_id=org_b)) as s:
        s.add(Organization(id=org_b, name="B"))
        s.flush()
        s.add(Membership(organization_id=org_b, user_id=user, role=Role.VIEWER.value))
    _create_org_with_member("C", "other@example.com")

    with session_scope(DbContext(user_id=user)) as s:
        orgs = set(s.execute(select(Membership.organization_id)).scalars())
        visible_orgs = set(s.execute(select(Organization.id)).scalars())
    assert orgs == {org_a, org_b}
    assert visible_orgs == {org_a, org_b}


def test_context_is_reapplied_on_every_transaction() -> None:
    org_a, _ = _create_org_with_member("A", "a@example.com")
    _create_org_with_member("B", "b@example.com")
    with get_sessionmaker()() as s:
        set_context(s, DbContext(organization_id=org_a))
        for _ in range(2):  # set_config(..., true) muere con cada transacción
            with s.begin():
                assert s.execute(select(Organization.id)).scalars().all() == [org_a]
