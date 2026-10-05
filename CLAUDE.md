# Reglas de trabajo (humanos y agentes)

Proyecto: SaaS para productoras de eventos. Propiedad de Julieta Arrazate, todos los derechos reservados.
Antes de cambiar algo, leé `docs/` (sobre todo `docs/product/DOMAIN_MODEL.md` y `docs/architecture/ARCHITECTURE.md`).

## Estructura

- `backend/` — FastAPI + SQLAlchemy 2 (sync) + Alembic, Python 3.12, gestionado con `uv`.
  - `src/app/core/` infraestructura · `src/app/domain/` dominio puro · `src/app/modules/<módulo>/` por dominio.
- `frontend/` — Next.js 16 (App Router), TypeScript strict, Tailwind, `pnpm`.
  - Next 16 tiene cambios incompatibles con versiones anteriores: leé `frontend/node_modules/next/dist/docs/` antes de usar una API.
- `infra/` — Docker Compose (Postgres 16, Mailpit) y blueprints de deploy.

## Comandos

`make check` corre lint, typecheck y tests de ambos lados (lo mismo que CI, sin build).
Backend: `cd backend && uv run pytest` (necesita Postgres; ver `backend/README.md`).

## Reglas no negociables

1. **Dinero:** `Decimal` siempre, nunca `float`. Los importes viajan como strings en JSON. El frontend no calcula dinero, solo formatea.
2. **Multi-tenant:** toda tabla de negocio lleva `organization_id`, FK compuestas y RLS (`FORCE`). Un ID de otra organización devuelve 404.
3. **Inmutabilidad:** historial de costos, versiones congeladas, propuestas y audit log no se modifican.
4. **Permisos en el servidor:** todo endpoint declara su permiso (`require(...)`) o se marca público explícitamente. Un test lo verifica.
5. **Límites entre módulos:** un módulo importa a otro solo por su paquete (`app.modules.x`), nunca sus submódulos internos.
6. **Migraciones** expand/contract, con `downgrade` probado.
7. **Nunca** saltear, deshabilitar ni poner en cuarentena un test para que CI pase.

## Cada cambio

Chico y verificable. La descripción del PR dice: qué resuelve, qué archivos toca, qué riesgos tiene, cómo se prueba y cómo se revierte.
Antes de pushear: lint, typecheck, tests y build en verde. **Nunca afirmar que algo funciona sin haberlo ejecutado.**
