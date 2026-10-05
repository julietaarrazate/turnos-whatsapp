# Deploy: staging y producción

> Estado: staging en **planes gratuitos** (D-18). Ver ARCHITECTURE §3.

```
Browser ──► Vercel (Next.js) ──/api/* rewrite──► Render (FastAPI, Docker) ──► Neon (Postgres 16)
                                                       │
                                                       ├─► Resend (email)
                                                       └─► Sentry (errores)
```

## 1. Neon (base de datos)

1. Crear el proyecto en **AWS us-east-1** (la misma región que la API).
2. Crear dos roles (como `neondb_owner`):
   ```sql
   CREATE ROLE app_migrator LOGIN PASSWORD '<generada>' NOSUPERUSER NOBYPASSRLS;
   CREATE ROLE app_runtime  LOGIN PASSWORD '<generada>' NOSUPERUSER NOBYPASSRLS;
   CREATE DATABASE app OWNER app_migrator;
   ```
3. Las URLs:
   - `MIGRATOR_DATABASE_URL`: rol `app_migrator`, endpoint **directo** (las migraciones usan DDL).
   - `DATABASE_URL`: rol `app_runtime`, endpoint **con pooler** (`-pooler` en el host). El contexto de tenant usa `set_config(..., true)`, que es compatible con PgBouncer en modo transacción.
4. Producción: desactivar el *scale to zero* (o aceptar ~0,5 s de cold start) y verificar la retención de PITR del plan.

## 2. Render (API)

1. New → **Blueprint** → este repo, con el path `infra/render.yaml`.
2. Cargar las variables `sync: false`:

| Variable | Valor |
|---|---|
| `DATABASE_URL` | URL de Neon con `app_runtime` (pooler) |
| `MIGRATOR_DATABASE_URL` | URL de Neon con `app_migrator` (directa) |
| `APP_BASE_URL` | `https://<dominio del frontend>` (links de los emails) |
| `ALLOWED_ORIGINS` | `["https://<dominio del frontend>"]` (JSON) |
| `EMAIL_FROM` | `Nombre <notificaciones@<tu-dominio>>` |
| `RESEND_API_KEY` | de Resend |
| `SENTRY_DSN` | proyecto Python en Sentry (opcional) |

3. Con `RUN_MIGRATIONS=true`, el contenedor corre `alembic upgrade head` antes de levantar la API (el plan free de Render no tiene pre-deploy command). Si la migración falla, el contenedor no arranca y Render mantiene la versión anterior. Por eso las migraciones son *expand/contract*. En un plan pago conviene usar `preDeployCommand: alembic upgrade head` y sacar la variable.
4. El health check es `/readyz`: verifica que la API llegue a la base.

## 3. Vercel (frontend)

1. Importar el repo con **Root Directory** = `frontend`.
2. Variables de entorno:

| Variable | Valor |
|---|---|
| `API_ORIGIN` | `https://<servicio>.onrender.com` |
| `NEXT_PUBLIC_SENTRY_DSN` / `SENTRY_DSN` | proyecto Next.js en Sentry (opcional) |
| `NEXT_PUBLIC_APP_ENV` / `APP_ENV` | `staging` o `production` |

3. Plan Hobby para desarrollo y piloto. Antes de cobrarle a una productora: **Pro** (Hobby no permite uso comercial).

## 4. Email (Resend)

Verificar tu dominio (SPF, DKIM y DMARC) y usar una dirección de ese dominio en `EMAIL_FROM`. Sin esto, los emails de invitación y reset caen en spam.

## 5. Primera organización

Desde una shell con las variables de producción:

```bash
cd backend
uv run python scripts/create_org.py --name "Productora X" --owner-email persona@x.com
```

El script crea la organización y envía la invitación de OWNER (y también imprime el link).

## 6. Después del primer deploy

- [ ] **Medir latencia desde Argentina** (D-18): `curl -w "%{time_total}\n" -o /dev/null -s https://<frontend>/api/v1/auth/me` desde una conexión local, 10 veces. Objetivo: p95 < 400 ms. Si no se cumple, se reabre D-18.
- [ ] Forzar un error de prueba y verificar que llega a Sentry con release y `request_id`, sin cookies, cuerpos ni tokens.
- [ ] Backup: confirmar PITR en Neon. El `pg_dump` nocturno a S3 se agrega cuando haya datos reales (Fase 3).
- [ ] Revisar los headers de seguridad en https://securityheaders.com.

## Limitaciones conocidas

- **Rate limiting en memoria:** vale mientras haya **una** instancia de la API. Con más instancias hace falta un store compartido (D-15).
- **IP del cliente:** se toma de `X-Forwarded-For` (Vercel la fija). Si alguien llama directo a la URL de Render, puede falsear la IP y saltear el límite *por IP*. El límite por email sigue vigente. Mitigación futura: aceptar solo tráfico que venga de Vercel.
