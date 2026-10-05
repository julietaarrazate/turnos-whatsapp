"""Helpers de migración para Row-Level Security y permisos (ver ARCHITECTURE §7.2-7.3)."""

from alembic import op

RUNTIME_ROLE = "app_runtime"


def enable_tenant_rls(table: str) -> None:
    """RLS forzada: el rol de runtime solo ve y escribe filas de la organización en contexto."""
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON {table} "
        "USING (organization_id = app_current_org()) "
        "WITH CHECK (organization_id = app_current_org())"
    )


def disable_tenant_rls(table: str) -> None:
    op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
    op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")


def grant_crud(table: str) -> None:
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {RUNTIME_ROLE}")


def grant_append_only(table: str) -> None:
    op.execute(f"GRANT SELECT, INSERT ON {table} TO {RUNTIME_ROLE}")
