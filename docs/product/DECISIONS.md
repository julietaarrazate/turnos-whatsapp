# DECISIONS — Registro de decisiones

> Estado: **borrador para aprobación** · Fecha: 2026-10-05
> Relacionados: [PRODUCT_SPEC](./PRODUCT_SPEC.md) · [ARCHITECTURE](../architecture/ARCHITECTURE.md) · [DOMAIN_MODEL](./DOMAIN_MODEL.md) · [MVP](./MVP.md)

**Estados:** ✅ decidida · 🟡 propuesta (aprobar o cambiar) · ❓ necesita tu input o el del piloto.

Las decisiones no se borran. Si cambian, se marcan como *reemplazada por D-xx* y se agrega la nueva.

---

## Preguntas abiertas

Son cosas que solo vos (o la productora del piloto) pueden responder. Ninguna bloquea el **PR 1.1** (esqueleto + CI). Las marcadas **⚑** sí bloquean la **Fase 2**.

| # | Pregunta | Por qué importa | Decisión afectada |
|---|---|---|---|
| Q1 | ¿Cómo se va a llamar el producto? | Repo, dominio, emails, PWA | D-02 |
| ~~Q2~~ | ~~¿MIT o "todos los derechos reservados"?~~ → **Respondida:** todos los derechos reservados | | D-03 |
| Q3 | ~~Régimen y costos con/sin IVA~~ → **Respondida:** Responsable Inscripto; costos cargados **sin IVA**; el presupuesto suma el IVA al final. *Pendiente:* qué cargos sobre la venta considera (IIBB, impuesto al cheque, comisiones). | | D-08 |
| Q4 | ~~¿USD?~~ → **Respondida:** reciben cotizaciones en pesos; ocasionalmente presentan el presupuesto en dólares a un cliente del exterior. | | D-09 |
| Q5 ⚑ | ¿Pueden pasarnos su **Excel de precios** y **3–5 presupuestos reales** (con costos y precio final), más una propuesta que hayan mandado? | Fixtures de importación y vectores dorados ("al centavo") | D-06, MVP §4 |
| Q6 | ¿Redondean los precios (a $100 o a $1.000)? ¿Muestran precio unitario, solo importes por línea o totales por rubro? | Política de redondeo y modo de propuesta por defecto | D-06, D-23 |
| Q7 | Un cliente con "markup preferencial", ¿pisa también el markup especial de un producto? | Precedencia de la cadena de markup | D-07 |
| Q8 | ¿Cómo aprueban hoy sus clientes (mail, OC, WhatsApp)? | Peso de la aprobación online frente a la manual | D-22 |
| Q9 | ¿Cuántas personas lo van a usar y quién **no** debería ver los márgenes? | Roles y redacción de campos | PRODUCT_SPEC §9 |
| ~~Q10~~ | ~~Presupuesto de infraestructura~~ → **Respondida:** planes gratuitos (Neon, Render, Vercel) | | D-18 |
| Q11 | ¿Tenés dominio propio? | Emails (SPF/DKIM), links públicos, cookies | D-13, D-18 |

---

## D-01 · Repositorio — ✅ decidida

Se usa este repositorio (`turnos-whatsapp`) como base del proyecto. El README ya describe el proyecto nuevo. Cuando se defina el nombre (D-02) se renombran el repo y la descripción de GitHub.

## D-02 · Nombre del producto — ❓

Pendiente (Q1). Mientras tanto, los documentos usan "la plataforma". El código va a usar un nombre de paquete neutro (`app`), así que renombrar después no cuesta nada.

## D-03 · Autoría, propiedad intelectual y licencia — ✅ decidida

- **La autoría y la propiedad intelectual del proyecto son de Julieta Arrazate.**
- **Licencia: todos los derechos reservados** (propietaria). Reemplaza a la MIT original, que era permisiva: le permitía a cualquiera con una copia usar, modificar y vender el código. Con el aviso propietario, nadie tiene permiso de uso sin autorización escrita de la titular.
- Complementos recomendados (fuera del código): registrar la obra en la Dirección Nacional del Derecho de Autor (DNDA) y firmar acuerdos de cesión de derechos y confidencialidad con cualquier persona que colabore en el código. Esto no es asesoramiento legal: conviene confirmarlo con un abogado.

## D-04 · Monolito modular — 🟡

- **Contexto:** son 25 módulos funcionales, para un equipo chico y un solo cliente piloto.
- **Opciones:** (a) monolito modular, (b) microservicios, (c) backend-as-a-service (Supabase o similar).
- **Recomendación: (a).** Un deploy, una base, transacciones simples entre módulos (aceptar una propuesta cambia el estado del evento en la misma transacción) y límites verificados con `import-linter`. Si algún módulo lo necesita, se puede extraer después.
- **Consecuencia:** hay que hacer cumplir la disciplina de módulos en CI.

## D-05 · El motor de pricing vive solo en el servidor — 🟡

- **Contexto:** el brief pide "no duplicar fórmulas en frontend y backend", y también feedback instantáneo en el editor.
- **Opciones:** (a) solo en el server, con recalculo por mutación; (b) duplicado en TS para cálculo optimista; (c) motor compilado a WASM o compartido.
- **Recomendación: (a).** Cada mutación devuelve la versión recalculada en una sola ida y vuelta. Los **vectores dorados** son JSON independientes del lenguaje, así que si la latencia medida no alcanza, se puede agregar un espejo TS **verificado contra los mismos vectores** en CI, sin abrir la puerta a dos verdades.
- **Disparador para revisar:** más de 400 ms end-to-end en staging desde Argentina (medido en la Fase 2).

## D-06 · Dinero y redondeo — 🟡 (validar con Q5 y Q6)

- `Decimal` en todo el backend, `NUMERIC` en la DB, strings en JSON y **nunca `float`**.
- Redondeo **HALF_UP** (comercial). Se redondea **el importe de la línea** (la unidad atómica) al **incremento comercial** configurable (0,01 por defecto). Los impuestos y cargos se redondean a 0,01.
- **Invariante:** Σ importes visibles = subtotal, exacto. El precio objetivo se reparte por mayor resto y da exacto.
- El precio unitario que ve el cliente es solo de presentación. Si no es exacto, la línea muestra cantidad e importe sin unitario.
- **Alternativa descartada:** redondear el precio unitario como unidad atómica. Hace imposible que un precio objetivo dé exacto con cantidades mayores a 1.

## D-07 · Precedencia del markup — 🟡 (validar con Q7)

- Cadena: `línea > presupuesto > cliente > producto > categoría > organización`, con el origen siempre visible.
- **Duda real:** si el cliente "Coca-Cola: 20%" debe pisar a un producto con markup especial del 60% (alquiler de equipo propio). Alternativa: reglas de cliente por categoría (`cliente + categoría`). Se decide con la respuesta del piloto. El modelo de datos (`markup_rules` con `scope`) soporta ambas variantes.
- **Cuándo se aplica:** al crear la línea. Un cambio de reglas no altera los borradores sin una acción explícita ("Re-aplicar reglas").

## D-08 · Impuestos y cargos sobre la venta — ✅ (régimen) · ❓ (cargos)

- **Piloto: Responsable Inscripto.** Los costos se cargan **netos de IVA** (como hoy) y el presupuesto se presenta como **subtotal + IVA = total**.
- El modelo igual guarda si un costo incluye IVA (para proveedores que facturan con IVA incluido o para futuras productoras monotributistas). El motor normaliza según el régimen de la organización (DOMAIN_MODEL §5.2, L1). La UI del MVP asume "sin IVA" por defecto.
- **Cargos sobre la venta** (IIBB, impuesto al cheque, comisiones): configurables. Falta saber cuáles usa el piloto (pregunta pendiente en Q3).
- **Fuera del MVP:** percepciones y retenciones, facturación electrónica (ARCA) y multi-jurisdicción de IIBB.

## D-09 · Moneda — ✅

- **Costos siempre en ARS** en el MVP (así cotizan los proveedores del piloto).
- El presupuesto se arma en ARS. **Opcionalmente se presenta en USD** (cliente del exterior): la versión guarda un tipo de cambio congelado y la propuesta muestra los importes convertidos. Cambiarlo es una acción explícita.
- Costos en USD por línea quedan para V2 (el modelo ya tiene `currency` en `price_history`, así que no requiere migración de datos).

## D-10 · Presupuesto → versión → propuesta (sin tablas `quotes`) — 🟡

- **Contexto:** el brief lista `budgets` / `budget_versions` **y** `quotes` / `quote_versions`. Son dos versionados del mismo contenido.
- **Recomendación:** `budget_versions` es el único versionado. Una **propuesta** es una *publicación* de una versión congelada (token, modo de presentación, vigencia, tracking, decisión). `quote_events` pasa a ser `proposal_activity`.
- **Consecuencia:** una sola verdad. Reenviar la misma versión con otra vigencia no crea una versión nueva.

## D-11 · Estados del evento — 🟡

- `LEAD → QUOTING → SENT → NEGOTIATION → APPROVED → IN_PRODUCTION → COMPLETED → CLOSED`, más `LOST` y `CANCELLED`.
- **Se elimina `DRAFT`** (es idéntico a `QUOTING`). **Se agrega `LOST`**: sin él no se distingue "el cliente eligió a otro" de "se canceló el evento", y la conversión no se puede medir.
- El evento existe desde el inicio. "Convertir a producción" es una **transición**, no una copia de datos.

## D-12 · Aislamiento multi-tenant — 🟡

- Tres capas: (1) filtrado obligatorio en la app, (2) **FK compuestas** `(organization_id, id)`, (3) **RLS** con `FORCE` y un rol de runtime sin privilegios de dueño.
- **Alternativas:** schema o base por tenant (operación cara, migraciones × N) o solo filtrado en la app (un bug alcanza para una fuga).
- RLS cuesta poco al inicio y es muy caro de agregar después. Es compatible con el pooler de Neon porque se usa `set_config(..., true)`, que es local a la transacción.

## D-13 · Autenticación — 🟡 (Q11)

- **Recomendación:** auth propia. argon2id, JWT de acceso de 15 min y refresh opaco rotativo con detección de reutilización, en **cookies httpOnly**. El browser llama a `/api/*` en el **mismo origen** y Next.js reescribe hacia Render (no hace falta CORS y los previews de Vercel funcionan).
- **Alternativa:** auth gestionada (Clerk, WorkOS, Neon Auth). Es más rápida de integrar y trae MFA y social login, pero agrega costo por usuario, dependencia y otro modelo de organizaciones a sincronizar.
- **Por qué propia:** son pocos usuarios, las organizaciones son núcleo del dominio y el brief pide JWT y refresh. El riesgo se mitiga con librerías probadas, tests y checklist ASVS (RT8).

## D-14 · Identificadores — 🟡

- PK **UUIDv7** (ordenable, no enumerable).
- **Numeración humana por organización** (`#1048` para presupuestos y eventos), con prefijo configurable. Lo que se comunica al cliente es el número, nunca el UUID.

## D-15 · Sin Redis ni colas en el MVP — 🟡

- Emails con **outbox** en Postgres + BackgroundTask + Render Cron para reintentos. PDF sincrónico cacheado. Rate limit en memoria (una instancia).
- **Disparadores para agregar Redis o un worker:** más de una instancia de API, PDF de más de 3 s o volumen de jobs que el cron no cubra.

## D-16 · Generación de PDF — 🟡

- **Recomendación:** **WeasyPrint** (HTML/CSS → PDF en Python). Sin navegador headless, menos memoria y buen soporte de CSS paginado.
- **Alternativa:** Playwright imprimiendo la página pública. Mayor fidelidad con el link, pero requiere Chromium en el server (~300–500 MB de RAM por instancia).
- **Consecuencia:** hay dos renderers de la misma propuesta (React para el link y Jinja para el PDF), alimentados por **el mismo snapshot JSON**. Se duplica presentación, no lógica de negocio. Un test verifica que ambos muestren los mismos importes.

## D-17 · Object storage — 🟡

- **Recomendación:** Cloudflare R2 (API S3, sin costo de egreso). Alternativa: AWS S3. El código usa la API S3 genérica (boto3) y se cambia de proveedor por configuración.

## D-18 · Hosting, región y costos — ✅ (planes gratuitos para staging y piloto)

- Vercel (frontend), Render (API) y Neon (Postgres), con **API y DB en us-east, co-ubicadas**.
- **Decisión:** se arranca con los **planes gratuitos** de los tres. Las consecuencias, aceptadas:
  - **Render free "duerme" tras ~15 min sin tráfico:** el primer request después tarda ~30–60 s. Para el piloto interno es tolerable; para propuestas a clientes reales (Fase 3) conviene pasar a Starter (~US$ 7/mes) o mantenerla despierta.
  - **Render free no tiene pre-deploy command:** las migraciones corren al arrancar el contenedor (`RUN_MIGRATIONS=true`), antes de levantar uvicorn. Si una migración falla, el contenedor no arranca y Render mantiene la versión anterior.
  - **Neon free** suspende el cómputo sin uso (cold start ~0,5 s) y tiene límites de horas y almacenamiento holgados para el piloto.
  - **Vercel Hobby** no permite uso comercial: alcanza para desarrollo y piloto; antes de cobrarle a una productora hay que pasar a Pro.
- Se mide la latencia desde Argentina con el sistema desplegado.

## D-19 · Acceso a datos sincrónico — 🟡

SQLAlchemy 2 **sincrónico** con psycopg 3 en el threadpool de FastAPI. El async ORM agrega fricción (lazy loading, `MissingGreenlet`) sin un beneficio real para la concurrencia de un B2B. Se puede migrar por módulo si algún día hace falta.

## D-20 · Stack de frontend — 🟡

Next.js App Router · TypeScript strict · Tailwind · componentes propios estilo shadcn/ui · **TanStack Query** · cliente **generado desde OpenAPI** (con chequeo de drift en CI) · parser numérico es-AR propio con tests.

*Actualización (Fase 1):* se usa **Next.js 16**. Para la PWA alcanza con el manifest nativo de Next más un service worker mínimo (página offline, sin cachear datos de la API). Serwist queda para cuando haga falta offline real (V2). Así no se depende de un plugin de build en el MVP. Los componentes base (botón, campos, switch) se escribieron a mano con Tailwind. Radix se suma cuando haga falta un primitivo complejo (menús, popovers).

## D-21 · Granularidad de presupuestado vs real — 🟡

- Un gasto **siempre** tiene evento y categoría. El proveedor y la línea presupuestada (`line_key`) son opcionales y se sugieren automáticamente.
- La comparación por categoría y por proveedor está siempre disponible. Por línea, cuando el gasto está vinculado. Lo que no tiene vínculo aparece como "No presupuestado".
- **Alternativa descartada:** exigir vínculo por línea. Es preciso, pero en campo nadie lo completaría (RP8).

## D-22 · Aprobación manual con OC en el MVP — 🟡 (Q8)

Los clientes corporativos aprueban con una orden de compra o por mail, no con un botón. Por eso en el MVP la aprobación manual (MANAGER+, con n° de OC y adjunto) tiene el mismo peso que la aceptación online.

## D-23 · Presentación de la propuesta — 🟡 (Q6)

Tres modos (detalle, por sección, solo total). Cada línea tiene **nombre interno** y **descripción para el cliente**. Las líneas pueden no mostrarse individualmente: se suman en su sección. El modo por defecto se configura por organización.

## D-24 · Idioma — 🟡

UI en español rioplatense (es-AR), con formatos vía `Intl` y zona `America/Argentina/Buenos_Aires`. Código, API y base en inglés. **Sin framework de i18n en el MVP**. La lógica fiscal está aislada detrás del "perfil fiscal" de la organización para habilitar otros países en el futuro.

## D-25 · IA — 🟡 (Fase 6)

Gateway con adaptadores intercambiables, salida estructurada validada, herramientas de solo lectura sobre el catálogo y **sin precios generados por el modelo**. Revisión humana obligatoria, logging de cada interacción y topes de costo por organización. Detalle en ARCHITECTURE §11.

## D-26 · El piloto arranca al cerrar la Fase 3 — 🟡

Cotizar y enviar es el mayor valor y el mayor riesgo de adopción. Esperar a tener producción, costos reales y analytics atrasaría el aprendizaje varios meses. Ver MVP §5.

---

## Qué dejamos configurable (y qué no)

### Configurable por organización (MVP)

| Grupo | Parámetros |
|---|---|
| Pricing | Markup general · markup o margen por categoría, producto y cliente · **margen mínimo** (aviso) · **incremento de redondeo** · si el margen objetivo compensa los cargos sobre la venta |
| Impuestos | Régimen IVA · alícuota por categoría o producto · **cargos sobre la venta** (nombre y %) · IVA en la propuesta por defecto (+IVA o incluido) |
| Monedas | Monedas habilitadas · tipo de cambio (manual, con historial) |
| Catálogo | Categorías · unidades · paquetes · tareas sugeridas por categoría · **umbral de antigüedad de costos** (días) |
| Propuestas | Vigencia por defecto · condiciones comerciales y forma de pago · modo de presentación por defecto · días de gracia del link vencido · logo y color |
| Seguimiento | Días sin respuesta para "para seguir" · horas para "vista sin respuesta" |
| Numeración | Prefijo de eventos y presupuestos |
| Visibilidad | Si VIEWER ve costos y márgenes |

### Configurable por presupuesto o propuesta

Moneda · tipo de cambio · modo de pricing (por línea, markup, margen objetivo, precio objetivo) · descuento global · días por línea · modo de presentación · IVA en la propuesta · vigencia · condiciones.

### Deliberadamente **no** configurable

| Qué | Por qué |
|---|---|
| Fórmulas y orden de operaciones del motor | Una sola verdad, testeada. La configuración cambia *parámetros*, no matemática. |
| Inmutabilidad de versiones congeladas, historial de costos y audit log | Es la base de la confianza y de la auditoría (P3) |
| Qué ve el cliente final | Nunca costo, proveedor, markup, margen ni notas internas. Sin excepciones. |
| Máquina de estados del evento | Las métricas (conversión, pipeline) dependen de estados consistentes. En V2 se podrían renombrar las etiquetas, no la lógica. |
| Modo de redondeo (HALF_UP) | Solo se configura el incremento |
| Roles (en el MVP) | Seis roles fijos y bien testeados valen más que roles personalizados a medias. Los personalizados quedan para V2. |
