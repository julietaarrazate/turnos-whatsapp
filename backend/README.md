# Backend

FastAPI + SQLAlchemy 2 (sync, psycopg 3) + Alembic. Python 3.12 con [uv](https://docs.astral.sh/uv/).

## Puesta en marcha

```bash
make up                         # desde la raíz: Postgres 16 + Mailpit (docker)
cd backend
uv sync
uv run alembic upgrade head     # como app_migrator
uv run uvicorn app.main:app --reload
```

Sin Docker: cualquier Postgres 16 local sirve. Ejecutá `infra/postgres/init.sql` como superusuario y habilitá `trust` para `127.0.0.1` en `pg_hba.conf` (en desarrollo no se usan contraseñas).

## Roles de base de datos

| Rol | Uso |
|---|---|
| `app_migrator` | Dueño del esquema. Solo migraciones (`MIGRATOR_DATABASE_URL`). |
| `app_runtime` | La aplicación (`DATABASE_URL`). No es dueño de las tablas y está sujeto a RLS. |

## Chequeos (lo mismo que CI)

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run lint-imports
uv run pytest          # usa la base app_test; necesita Postgres
```
