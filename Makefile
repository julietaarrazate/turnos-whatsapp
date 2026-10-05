# Comandos de desarrollo. Requiere: uv, pnpm, docker (o un Postgres 16 local).
.PHONY: up down install dev-api dev-web lint typecheck test check openapi

up:            ## Levanta Postgres y Mailpit
	docker compose -f infra/docker-compose.yml up -d --wait

down:
	docker compose -f infra/docker-compose.yml down

install:
	cd backend && uv sync
	cd frontend && pnpm install --frozen-lockfile

dev-api:
	cd backend && uv run uvicorn app.main:app --reload --port 8000

dev-web:
	cd frontend && pnpm dev

lint:
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run lint-imports
	cd frontend && pnpm lint

typecheck:
	cd backend && uv run mypy
	cd frontend && pnpm typecheck

test:
	cd backend && uv run pytest
	cd frontend && pnpm test

check: lint typecheck test   ## Lo mismo que corre CI (sin build ni e2e)
