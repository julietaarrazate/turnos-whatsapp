# Deploy: staging y producción

> Regla: **todo en planes gratuitos**, también producción (D-18). Ver ARCHITECTURE §3.

## Estado actual (staging)

| Pieza | Dónde | Estado |
|---|---|---|
| Base de datos | Neon, proyecto `productoras-staging` (aws-us-east-1, Postgres 16), base `app` | ✅ Roles `app_migrator`/`app_runtime` creados por SQL (sin privilegios de Neon). Migraciones en 0003. RLS forzada verificada. |
| API | Render, `productoras-api-staging` (Virginia, free, Docker), https://productoras-api-staging.onrender.com | ✅ En línea. Migra al arrancar. Despliega la rama `claude/happy-maxwell-isce4u`, que el workflow `sync-render.yml` adelanta a `main` en cada push: backend y frontend quedan siempre en la misma versión, sin tocar Render. |
| Frontend | Vercel, `productoras-web` (Hobby, Root Directory `frontend`, Next.js), https://productoras-web.vercel.app | ✅ En línea. Despliega `main` a producción. |
| Email | — | Consola (sin Resend). Las invitaciones muestran su link en la app para mandarlo por WhatsApp; el de cambio de contraseña queda solo en los logs de Render. |
| Archivos (comprobantes, OC) | — | Apagado hasta crear el bucket (sección 4b). La app no muestra "adjuntar". |
| Backup diario | GitHub Actions → bucket | Apagado hasta cargar los secrets (sección 7). Mientras tanto, solo el restore de Neon (6 horas). |
| Primera organización | "Productora piloto" (RI) | ✅ La titular aceptó la invitación de OWNER (verificado en logs: invitación → aceptación → /me, todo 200). |

Las credenciales viven solo en las variables de entorno de Render. No están en el repo.

```
Browser ──► Vercel (Next.js) ──/api/* rewrite──► Render (FastAPI, Docker) ──► Neon (Postgres 16)
                                                       │
                                                       ├─► Resend (email)
                                                       ├─► R2 / S3 (comprobantes y OC)
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
4. Plan gratis: el cómputo se suspende a los 5 min sin uso (al volver tarda ~0,5 s). Conviene así: las horas de cómputo gratis (100 por mes) se gastan solo mientras se usa. El restore de Neon llega a 6 horas atrás; para más, está el backup diario (sección 7).
5. El rol dueño que crea Neon (`neondb_owner`; en staging se llama `app_bootstrap_owner`) puede leer todas las filas (BYPASSRLS). La app no lo usa: solo el backup.

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
| `STORAGE_BACKEND`, `S3_*` | ver sección 4b (opcional: sin esto no se adjuntan archivos) |

3. Con `RUN_MIGRATIONS=true`, el contenedor corre `alembic upgrade head` antes de levantar la API (el plan free de Render no tiene pre-deploy command). Si la migración falla, el contenedor no arranca y Render mantiene la versión anterior. Por eso las migraciones son *expand/contract*. En un plan pago conviene usar `preDeployCommand: alembic upgrade head` y sacar la variable.
4. El health check es `/healthz`, que **no toca la base**. Render lo consulta seguido mientras la API está despierta: si fuera `/readyz`, Neon no se suspendería nunca y gastaría sus horas gratis. Si el servicio se creó antes de este cambio y no sigue el Blueprint, cambiarlo a mano en Render → *Settings* → *Health Check Path*. `/readyz` (que sí verifica la base) queda para chequeos manuales.

## 2b. Que la API no se duerma (opcional, gratis)

El plan free de Render apaga la API a los 15 min sin tráfico y la primera visita después tarda ~1 min. Para evitarlo en horario de trabajo, un servicio gratuito como [cron-job.org](https://cron-job.org) puede llamarla cada 10 min:

- URL: `https://<servicio>.onrender.com/healthz` (no `/readyz`: despertaría la base para nada).
- Horario: por ejemplo de lunes a sábado de 8 a 22 (hora de Argentina). **No las 24 horas:** las 750 horas gratis por mes son de todo el workspace de Render; un servicio despierto todo el mes usa ~744 y, si hay otros servicios gratis en el mismo workspace, se suspenden todos hasta el mes siguiente. De 8 a 22, seis días por semana, son ~360 horas.
- Fuera de ese horario, la primera visita tarda ~1 min. Un cliente que abre una propuesta a la noche espera ese minuto.

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

**Sin dominio (todo gratis):** se queda `EMAIL_BACKEND=console`. Al invitar a alguien, la app muestra el link para copiarlo o mandarlo por WhatsApp (una sola vez; invitar de nuevo al mismo email anula el anterior). Las propuestas ya se comparten por link o WhatsApp. Lo que no tiene alternativa todavía es "olvidé mi contraseña": ese link queda solo en los logs de Render. **Gmail no sirve:** Render free bloquea los puertos de email (SMTP).

## 4b. Archivos: comprobantes y OC (Cloudflare R2)

Sin configurar, la app funciona igual pero no deja adjuntar la foto del comprobante ni la OC (D-17). Para activarlo con R2 (10 GB gratis, sin costo de egreso):

1. Cloudflare → **R2** → *Create bucket* (por ejemplo `productoras-archivos`). Dejarlo **privado**: sin dominio público ni acceso público. No hace falta configurar CORS (los archivos pasan por la API).
2. R2 → *Manage API tokens* → *Create API token* con permiso **Object Read & Write** limitado a ese bucket. Guardar el *Access Key ID* y el *Secret Access Key* (se muestran una sola vez).
3. En Render, cargar:

| Variable | Valor |
|---|---|
| `STORAGE_BACKEND` | `s3` |
| `S3_BUCKET` | el nombre del bucket |
| `S3_ENDPOINT_URL` | `https://<account_id>.r2.cloudflarestorage.com` (está en la página del bucket) |
| `S3_REGION` | `auto` |
| `S3_ACCESS_KEY_ID` / `S3_SECRET_ACCESS_KEY` | los del token |

4. Verificar: en un evento aprobado, cargar un gasto con una foto y abrir "Comprobante".

Con AWS S3 es igual: `S3_ENDPOINT_URL` vacío, `S3_REGION` la del bucket y un usuario IAM con `s3:GetObject` y `s3:PutObject` sobre ese bucket. `STORAGE_BACKEND=local` no se acepta fuera de desarrollo: el disco de Render se borra en cada deploy.

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
- [ ] Backup: cargar los secrets (sección 7), correrlo a mano una vez y verificar el archivo en el bucket.
- [ ] Revisar los headers de seguridad en https://securityheaders.com.

## 7. Backups y restore

Neon gratis permite volver solo 6 horas atrás. El workflow `.github/workflows/backup.yml` corre todos los días a las 03:17 (Argentina) y también a mano (*Actions* → *Backup* → *Run workflow*). Cada corrida:

1. Hace `pg_dump` de la base.
2. **Lo restaura** en un Postgres vacío del runner (con los mismos roles que la base real) y compara las filas tabla por tabla. Si no coincide, falla. Es el simulacro de restore, todos los días.
3. Lo cifra (gpg, AES-256) y lo sube al bucket como `backups/app-AAAA-MM-DD.dump.gpg`.
4. Borra los de más de 30 días.

Gratis: ~1-2 minutos de Actions por día (el repo privado tiene 2.000 por mes) y ~1-2 MB por día en el bucket. Si una corrida falla, GitHub te manda un email.

**Configurar** (GitHub → el repo → *Settings* → *Secrets and variables* → *Actions* → *New repository secret*):

| Secret | Valor |
|---|---|
| `BACKUP_DATABASE_URL` | Neon → *Connect* → rol **dueño** (`neondb_owner`; en staging, `app_bootstrap_owner`), base `app`, conexión **directa** (sin `-pooler`). `app_migrator` y `app_runtime` no sirven: están sujetos a RLS y el backup sale vacío o falla. |
| `BACKUP_PASSPHRASE` | Una clave larga al azar. **Guardala también en tu gestor de contraseñas:** sin ella los backups no se pueden abrir. |
| `S3_BUCKET`, `S3_ENDPOINT_URL`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` | Los mismos del bucket de la sección 4b (los backups van a la carpeta `backups/`). |

Sin estos secrets, el workflow termina en verde con un aviso y no hace nada.

**Restaurar** (si se perdió o se rompió la base):

```bash
# 1. Bajar el archivo del bucket (Cloudflare → R2 → el bucket → backups/) y descifrarlo
gpg --decrypt --output app.dump app-AAAA-MM-DD.dump.gpg     # pide BACKUP_PASSPHRASE
# 2. En Neon, crear una base vacía cuyo dueño sea app_migrator (por ejemplo, app_restore)
# 3. Restaurar como app_migrator: tablas, datos, RLS y permisos de app_runtime quedan como estaban
pg_restore --no-owner --exit-on-error --dbname="<URL directa de app_migrator a app_restore>" app.dump
```

Después, apuntar `DATABASE_URL` y `MIGRATOR_DATABASE_URL` de Render a la base nueva y redeployar. Este procedimiento exacto está cubierto por `backend/tests/ops/test_backup.py`.

Backup a mano, en tu computadora (sin bucket): `BACKUP_DATABASE_URL=... BACKUP_PASSPHRASE=... uv run python scripts/backup.py --output <carpeta>`.

## Limitaciones conocidas

- **Rate limiting en memoria:** vale mientras haya **una** instancia de la API. Con más instancias hace falta un store compartido (D-15).
- **IP del cliente:** se toma de `X-Forwarded-For` (Vercel la fija). Si alguien llama directo a la URL de Render, puede falsear la IP y saltear el límite *por IP*. El límite por email sigue vigente. Mitigación futura: aceptar solo tráfico que venga de Vercel.
