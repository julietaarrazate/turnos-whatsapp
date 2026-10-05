# MVP — Alcance exacto, V2 y plan de implementación

> Estado: **borrador para aprobación** · Fecha: 2026-10-05
> Relacionados: [PRODUCT_SPEC](./PRODUCT_SPEC.md) · [ARCHITECTURE](../architecture/ARCHITECTURE.md) · [DOMAIN_MODEL](./DOMAIN_MODEL.md) · [DECISIONS](./DECISIONS.md)

---

## 1. Objetivo del MVP

> **Una productora real (la del piloto) deja de usar Excel para presupuestar.** Arma presupuestos desde su catálogo en minutos, envía propuestas profesionales por WhatsApp o email, el cliente las aprueba y, para cada evento aprobado, sabe cuánto presupuestó, cuánto gastó y cuánto ganó.

### Hipótesis a validar

| # | Hipótesis | Señal de éxito en el piloto |
|---|---|---|
| H1 | Con catálogo + paquetes se presupuesta más rápido que en Excel | Presupuesto típico en < 10 min (contra la línea de base medida en Excel) |
| H2 | El catálogo se puede mantener al día con aumentos masivos y avisos de antigüedad | ≥ 80% de las líneas enviadas usan costos de menos de 30 días |
| H3 | Los clientes usan el link (o, si no, la aprobación manual cubre la realidad) | 100% de las aprobaciones quedan registradas en el sistema (online + manual) |
| H4 | Producción carga costos reales si es rápido desde el celular | ≥ 80% de los eventos aprobados con costos reales |
| H5 | El dueño usa el dashboard para decidir | Uso semanal y feedback cualitativo |

### Usuario del MVP

**Una organización** (la productora del piloto), de 2 a 6 usuarios, creada por script. El sistema es **multi-tenant desde el día 1** (aislamiento completo y testeado), pero **sin registro self-service ni billing**.

---

## 2. Alcance exacto del MVP

Cada ítem tiene un ID para seguirlo en los PRs. "✓ criterio" = criterio de aceptación verificable.

### 2.1 Fundación

| ID | Funcionalidad | Criterio de aceptación |
|---|---|---|
| F-01 | Login con email y contraseña, logout, sesión persistente (refresh rotativo) | ✓ La sesión dura 30 días con uso. ✓ Reusar un refresh token revoca la sesión. ✓ Rate limit en login. |
| F-02 | Invitar usuarios por email con rol · aceptar invitación · reset de contraseña | ✓ El token es de un solo uso, vence y se guarda hasheado |
| F-03 | 6 roles fijos con la matriz de PRODUCT_SPEC §9 | ✓ Test generado desde la matriz (rol × endpoint). ✓ PRODUCTION nunca recibe campos de margen. |
| F-04 | Multi-tenancy con aislamiento en tres capas | ✓ Suite parametrizada: todas las rutas × IDs de otra organización → 404. ✓ Toda tabla con `organization_id` tiene RLS. |
| F-05 | Audit log de las acciones de DOMAIN_MODEL §7 | ✓ Se escribe en la misma transacción. ✓ El rol de la app no puede hacer UPDATE ni DELETE. |
| F-06 | Configuración de la organización: datos fiscales, régimen IVA, marca (logo y color), condiciones y vigencia por defecto, redondeo, margen mínimo, umbral de antigüedad | ✓ Los cambios quedan auditados |
| F-07 | PWA instalable, layout mobile (tab bar) y desktop (sidebar), búsqueda global ⌘K | ✓ Lighthouse PWA instalable. ✓ Navegación completa con teclado. |
| F-08 | Observabilidad (Sentry FE/BE, logs estructurados, health checks) y deploy de staging y producción | ✓ Un error de prueba aparece en Sentry con release y `request_id` |

### 2.2 Núcleo comercial

| ID | Funcionalidad | Criterio de aceptación |
|---|---|---|
| C-01 | **Clientes**: CRUD, contactos, notas, soft delete | ✓ Se puede crear inline desde "Nuevo presupuesto" con solo el nombre |
| C-02 | **Historial del cliente**: eventos, presupuestos, # aceptados y perdidos, conversión, facturado (aceptado sin IVA), margen promedio ponderado | ✓ Coincide con las definiciones de PRODUCT_SPEC §8 |
| C-03 | **Proveedores**: CRUD, contactos, rubros, condiciones de pago, evaluación 1–5 ★, proveedor interno "Equipo propio" | |
| C-04 | **Categorías y unidades** editables (con semilla inicial) | |
| C-05 | **Productos**: CRUD, categoría, unidad, modo de cobro (fijo / por día), descripciones interna y para el cliente, cantidad mínima, IVA, activo | |
| C-06 | **Ofertas de proveedor** e **historial de costos** append-only (moneda, ¿incluye IVA?, vigente desde, origen) | ✓ Editar un costo **crea** un registro (0 UPDATEs, verificado por trigger). ✓ Se permiten fechas futuras. |
| C-07 | **"¿Quién me ofrece esto?"**: ofertas vigentes ordenadas por costo, con antigüedad y ★ | |
| C-08 | **Aviso de costo desactualizado** (> N días) en el catálogo y en las líneas | |
| C-09 | **Importar catálogo** desde XLSX o CSV: mapeo de columnas, vista previa, errores por fila, simulación, confirmación | ✓ El Excel real del piloto se importa sin edición manual previa (o con errores claros por fila) |
| C-10 | **Aumento masivo** por proveedor o categoría (% y fecha de vigencia) | ✓ Crea N registros nuevos. ✓ Los presupuestos enviados no cambian. |
| C-11 | **Reglas de markup**: organización, categoría, producto, cliente (markup o margen) | ✓ La cadena de DOMAIN_MODEL §5.3 con origen visible |
| C-12 | **Cargos sobre la venta** (IIBB, etc.) y **tipo de cambio USD** manual con historial | |
| C-13 | **Motor de pricing** completo según DOMAIN_MODEL §5: markup, margen objetivo (con cargos), precio objetivo con reparto exacto, descuento por línea y global, IVA, USD, redondeo comercial | ✓ Vectores V01–V15 en verde. ✓ Tests de propiedades. ✓ 100% de branches cubiertos. |

### 2.3 Presupuestos

| ID | Funcionalidad | Criterio de aceptación |
|---|---|---|
| B-01 | **Nuevo presupuesto** en un flujo: cliente → evento (fecha opcional, días) → editor | ✓ Crea el evento en `QUOTING` |
| B-02 | **Editor desktop**: secciones, líneas del catálogo y libres, buscador, teclado primero, panel de detalle, reordenar, deshacer | ✓ Journey J2 en E2E |
| B-03 | **Editor mobile**: tarjetas, bottom sheet de línea, pie fijo con costo, venta, ganancia y margen | ✓ Journey J2 en E2E con viewport de iPhone |
| B-04 | **Recalculo server-side** con autoguardado, lock optimista e idempotencia | ✓ ≤ 400 ms end-to-end en staging desde AR (medido) |
| B-05 | **Modos a nivel presupuesto**: markup global, margen objetivo, precio objetivo (con líneas bloqueadas) | ✓ V09 reproducido desde la UI |
| B-06 | **Paquetes**: CRUD e insertar (expande líneas en secciones con días según regla) | |
| B-07 | **Duplicar presupuesto** de otro evento (con costos actuales y aviso de diferencias) | |
| B-08 | **Actualizar costos** y **re-aplicar reglas** como acciones explícitas con diff | ✓ Caso obligatorio 1 y 3 de ARCHITECTURE §13.3 |
| B-09 | **Versiones**: congelar (al enviar o manual), nueva versión, historial | ✓ Trigger de inmutabilidad. ✓ Caso obligatorio 4. |
| B-10 | **Comparar versiones** (agregadas, quitadas, modificadas y deltas) | |
| B-11 | **Exportar a Excel** la versión interna (con costos y márgenes, según permisos) | |
| B-12 | **Pipeline de presupuestos**: lista con estado derivado (borrador, enviado, visto, negociación, aceptado, perdido) y filtros | |

### 2.4 Propuestas

| ID | Funcionalidad | Criterio de aceptación |
|---|---|---|
| P-01 | **Generar propuesta** de una versión congelada: modo de presentación (detalle, por sección, solo total), IVA (+IVA o incluido), vigencia, condiciones y forma de pago | |
| P-02 | **Link público** con token seguro, página SSR mobile-first con la marca de la productora | ✓ LCP < 2,5 s en 4G. ✓ Caso obligatorio 6 (sin claves ni valores internos en JSON, HTML y PDF). |
| P-03 | **PDF** idéntico en contenido al link | ✓ Se cachea por hash |
| P-04 | **Compartir**: WhatsApp (share nativo o `wa.me` con mensaje), email (Resend), copiar link · OG sin montos | |
| P-05 | **Aceptar o rechazar online** con nombre, email y comentario · evidencia (IP, UA, hash) | ✓ Idempotente. ✓ El evento pasa a `APPROVED`. |
| P-06 | **Aprobación manual** con n° de OC y adjunto (MANAGER+) | |
| P-07 | **Tracking**: enviada, vista (primera, última, cantidad), PDF descargado | |
| P-08 | **Vencimiento**, **reemplazo** al enviar otra y **anulación** | ✓ Máquina de estados de DOMAIN_MODEL §3.3 |
| P-09 | **Notificaciones por email**: vista (primera vez), aceptada, rechazada | ✓ Outbox con reintentos |

### 2.5 Operaciones y rentabilidad

| ID | Funcionalidad | Criterio de aceptación |
|---|---|---|
| O-01 | **Evento**: ficha con pestañas, máquina de estados completa (incluye `LOST` con motivo y `CANCELLED`) | ✓ Transiciones inválidas → error. ✓ Historial de estados. |
| O-02 | **Iniciar producción**: lista de contratación por proveedor derivada de la baseline + estados | ✓ Sin re-carga: cada ítem viene de la versión aceptada |
| O-03 | **Tareas** simples (título, responsable, fecha, estado) con sugeridas por categoría | |
| O-04 | **Gastos reales** desde el celular: monto, moneda, proveedor, categoría, línea (opcional, sugerida), foto del comprobante | ✓ Journey J6 en ≤ 3 pantallas. ✓ Idempotente. |
| O-05 | **Presupuestado vs real** por categoría, proveedor y línea, con "no presupuestado" | ✓ V13 reproducido |
| O-06 | **Rentabilidad del evento**: estimada vs real (venta neta, costo, cargos, ganancia, margen) · cierre (`CLOSED`) | ✓ V14 reproducido |
| A-01 | **Dashboard**: enviado, aceptado, en negociación, margen promedio, conversión + "para hacer hoy" + próximos eventos | ✓ Métricas según PRODUCT_SPEC §8 (test con datos sembrados) |
| A-02 | **Reportes**: rentabilidad por evento, por cliente y por período (tabla + export CSV) | |

### 2.6 Explícitamente fuera del MVP

- Registro self-service, billing del SaaS, roles personalizados, MFA y login con Google.
- IA (toda la Fase 6).
- Facturación electrónica (ARCA), cobranzas, cuentas por cobrar y pagar, flujo de caja.
- Órdenes de compra a proveedores, pedidos de cotización (RFQ) y portal de proveedor.
- Crew y personal con horarios, logística, calendario.
- Opciones o alternativas dentro de una misma propuesta (Opción A / B), líneas opcionales que el cliente elige.
- Paquetes paramétricos (medidas → cantidades) y paquetes a precio cerrado.
- Bloqueo por margen mínimo con flujo de aprobación (en el MVP solo hay aviso).
- Tipo de cambio automático (BNA / MEP).
- Modo offline con edición. Notificaciones push e in-app. WhatsApp Business API.
- Rentabilidad por categoría, proveedor y usuario (los datos quedan guardados, falta la vista).
- Multi-idioma y multi-país (impuestos de otros países).

---

## 3. V2 (después del MVP, priorizado con el piloto)

| Prioridad tentativa | Bloque | Contenido |
|---|---|---|
| Alta | **IA (Fase 6)** | Texto libre → borrador de presupuesto con productos del catálogo · matching de productos · detección de anomalías (costos fuera de rango, desvíos) · asistencia de pricing ("presupuestos similares se cerraron con 27% de margen") |
| Alta | **Comercial avanzado** | Alternativas y líneas opcionales en la propuesta · margen mínimo con aprobación · órdenes de cambio (adicionales) formales · paquetes paramétricos |
| Alta | **Proveedores** | Órdenes de compra · pedidos de cotización con tiempo de respuesta · comparación de cotizaciones |
| Media | **Finanzas** | Cobranzas y cuentas por cobrar · pagos a proveedores · flujo de caja por evento · integración con facturación electrónica (ARCA) o export a sistemas contables (Xubio, Colppy, Tango) |
| Media | **Operaciones** | Crew y personal, calendario, logística, documentos operativos, modo offline (lectura del día + cola de gastos) |
| Media | **Analytics** | Rentabilidad por categoría, proveedor y vendedor · tendencias · forecast del pipeline |
| Media | **Plataforma SaaS** | Registro self-service, onboarding guiado, billing, roles personalizados, MFA, Google login, dominio de email propio por productora |
| Baja | **Integraciones** | WhatsApp Business API, Google Calendar, firma electrónica, tipo de cambio automático |

---

## 4. Definición de "MVP listo"

1. Todos los IDs de §2.1–2.5 implementados, con sus criterios de aceptación verificados.
2. CI en verde con todas las compuertas de ARCHITECTURE §12.2. E2E de J2, J3, J4 y J6 en mobile y desktop.
3. **3–5 presupuestos reales del piloto reproducidos al centavo** (vectores dorados).
4. Seis casos obligatorios del brief cubiertos por tests (ARCHITECTURE §13.3).
5. Producción desplegada con backups verificados (**simulacro de restore hecho**) y checklist de seguridad (ASVS L2 básico) revisado.
6. El piloto usó el sistema para **todos** sus presupuestos durante al menos 4 semanas.

---

## 5. Plan de implementación por fases

**El piloto real arranca al cerrar la Fase 3.** Ahí ya se puede cotizar y enviar, que es el mayor valor y donde está el mayor riesgo de adopción. Las Fases 4 y 5 se construyen con el piloto ya en uso.

```
Fase 0  Diseño aprobado + insumos del piloto
Fase 1  Fundación                         ──┐
Fase 2  Núcleo comercial + motor          ──┼── "MVP comercial" → PILOTO EMPIEZA
Fase 3  Salida comercial (propuestas)     ──┘
Fase 4  Operaciones (producción, costos reales, BvA)
Fase 5  Analytics (dashboard, reportes)   ──── MVP completo
Fase 6  IA                                ──── V2
```

### Reglas para cada PR (§30 del brief)

Cada PR es chico y verificable, y su descripción responde:

1. **Qué problema resuelve** (IDs de este documento).
2. **Qué archivos modifica.**
3. **Qué riesgos introduce.**
4. **Cómo se prueba** (tests nuevos + evidencia: salida de tests, typecheck, lint, build y migraciones).
5. **Cómo revertirlo** (revert del commit; si hay migraciones, `alembic downgrade` probado en CI).

Nunca se afirma que algo funciona sin haberlo ejecutado.

### Fase 0 — Diseño e insumos (esta etapa)

- Aprobar estos documentos y resolver las preguntas abiertas de [DECISIONS](./DECISIONS.md#preguntas-abiertas).
- **Pedirle al piloto:** su Excel de precios actual, 3–5 presupuestos reales (con costos y precios finales), una propuesta que hayan mandado a un cliente (PDF) y, si hay, una OC de un cliente corporativo.
- Medir la **línea de base**: cuánto tarda hoy en armar un presupuesto típico.

### Fase 1 — Fundación

| PR | Contenido | Tamaño | Riesgo principal | Cómo se prueba |
|---|---|:-:|---|---|
| 1.1 | Esqueleto: `backend/` (uv, FastAPI, ruff, mypy, pytest), `frontend/` (Next, TS strict, Tailwind, ESLint, Vitest), `infra/docker-compose.yml`, `Makefile`, `ci.yml`, `CLAUDE.md` | M | Ninguno (aditivo) | CI en verde. `make dev` levanta todo. |
| 1.2 | Base de datos: SQLAlchemy, Alembic, convenciones, UUIDv7, roles `app_runtime` / `app_migrator`, `organizations` / `users` / `memberships`, contexto de tenant, helper de RLS | M | Mala configuración de RLS | Test "toda tabla tenant tiene RLS". Test de RLS directo en la DB. `upgrade/downgrade` en CI. |
| 1.3 | Auth: login, refresh rotativo, logout, invitaciones, reset, outbox de email (Mailpit local), rate limit | L | Seguridad de sesión | Tests de rotación, reutilización, expiración y rate limit |
| 1.4 | RBAC + audit log + **harness de aislamiento** (parametrizado sobre rutas) + test "toda ruta declara permiso" | M | Que haya huecos de permisos | Los harness mismos |
| 1.5 | Shell del frontend: auth, layout mobile y desktop, tokens, shadcn base, cliente generado + chequeo de contrato, PWA (Serwist), formatters y parser es-AR | L | Deuda de UX temprana | Vitest (parser con decenas de casos), Playwright de humo |
| 1.6 | Observabilidad y deploy: Sentry, structlog, `/healthz`, Dockerfile, `render.yaml`, Vercel, staging · **medir latencia desde AR** | M | Costos y regiones | Error de prueba en Sentry. Medición documentada. |

**Salida de la Fase 1:** login en staging desde el celular. CI con todas las compuertas. Harness de tenants y permisos corriendo. Latencia medida y D-18 confirmada o revisada.

### Fase 2 — Núcleo comercial

| PR | Contenido | Tamaño |
|---|---|:-:|
| 2.1 | **Motor de pricing puro** + vectores V01–V15 + propiedades (hypothesis). **Va antes que cualquier pantalla.** | M |
| 2.2 | Clientes y contactos (API + UI) | M |
| 2.3 | Proveedores, contactos, rubros, evaluación · categorías y unidades | M |
| 2.4 | Productos, ofertas, `price_history` (trigger append-only), costo vigente, antigüedad, "¿quién lo ofrece?" | L |
| 2.5 | Reglas de markup, cargos sobre la venta, tipo de cambio, configuración de pricing | M |
| 2.6 | Importación XLSX/CSV con simulación + aumento masivo | L |
| 2.7 | Eventos (alta, `LEAD` / `QUOTING`) + presupuestos + borrador + API de secciones y líneas con recalculo, lock optimista e idempotencia | L |
| 2.8 | Editor desktop | L |
| 2.9 | Editor mobile | L |
| 2.10 | Paquetes, duplicar presupuesto, actualizar costos, re-aplicar reglas | M |

**Salida de la Fase 2:** los presupuestos reales del piloto reproducidos al centavo. Tiempo de armado medido con el usuario real (hipótesis H1). Si la latencia del editor no cumple, se reabre D-05.

### Fase 3 — Salida comercial → **arranca el piloto**

| PR | Contenido | Tamaño |
|---|---|:-:|
| 3.1 | Congelar versiones (triggers), historial y comparador | M |
| 3.2 | Propuesta: snapshot público por lista blanca, token, página SSR, **tests de visibilidad** | L |
| 3.3 | Aceptar, rechazar, vencer, reemplazar, anular · aprobación manual con OC · transiciones del evento · notificaciones | L |
| 3.4 | PDF (WeasyPrint) con marca, condiciones y cache | M |
| 3.5 | Compartir (WhatsApp, email, link), OG, exportar a Excel | S |
| 3.6 | Pipeline de presupuestos y "para seguir" básico | M |

**Salida de la Fase 3:** producción desplegada, backups y simulacro de restore, revisión de seguridad. **El piloto manda propuestas reales desde el sistema.**

### Fase 4 — Operaciones

| PR | Contenido | Tamaño |
|---|---|:-:|
| 4.1 | Máquina de estados completa del evento + ficha con pestañas | M |
| 4.2 | Iniciar producción: lista de contratación y tareas | M |
| 4.3 | Gastos reales mobile-first + upload de comprobantes (S3 presignado) | M |
| 4.4 | Presupuestado vs real + rentabilidad del evento + cierre | M |

### Fase 5 — Analytics → **MVP completo**

| PR | Contenido | Tamaño |
|---|---|:-:|
| 5.1 | Dashboard (KPIs según definiciones) + "para hacer hoy" + próximos eventos | M |
| 5.2 | Historial comercial del cliente + reportes por evento, cliente y período | M |

### Fase 6 — IA (inicio de V2)

| PR | Contenido |
|---|---|
| 6.1 | AI Gateway + adaptador del proveedor + logging de interacciones + topes de costo |
| 6.2 | Matching de productos (pg_trgm + full-text) |
| 6.3 | Texto libre → `BudgetDraft` → revisión humana → inserción en el editor |
| 6.4 | Detección de anomalías (costos atípicos, desvíos) y asistencia de pricing |

---

## 6. Qué hacemos inmediatamente después de aprobar

1. Resolver las preguntas abiertas de DECISIONS (sobre todo: régimen fiscal del piloto, USD, presupuestos reales).
2. Arrancar el **PR 1.1** (esqueleto + CI), y recién después el resto en el orden de la tabla.
