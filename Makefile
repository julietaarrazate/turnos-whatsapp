# Comandos de desarrollo. Requiere: uv, pnpm, docker (o un Postgres 16 local).
.PHONY: up down install migrate seed dev-api dev-web lint typecheck test check

up:            ## Levanta Postgres y Mailpit
	docker compose -f infra/docker-compose.yml up -d --wait

down:
	docker compose -f infra/docker-compose.yml down

install:
	cd backend && uv sync
	cd frontend && pnpm install --frozen-lockfile

migrate:
	cd backend && uv run alembic upgrade head

seed:          ## Organización demo con un usuario por rol
	cd backend && uv run python scripts/seed_dev.py

dev-api:
	cd backend && uv run uvicorn app.main:app --reload --port 8000

dev-web:
	cd frontend && pnpm dev

lint:
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run lint-imports && uv run python scripts/check_module_boundaries.py
	cd frontend && pnpm lint

typecheck:
	cd backend && uv run mypy
	cd frontend && pnpm typecheck

test:
	cd backend && uv run pytest
	cd frontend && pnpm test

check: lint typecheck test   ## Lo mismo que corre CI (sin build ni e2e)
