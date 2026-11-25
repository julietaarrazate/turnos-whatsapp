import { expect, test, type APIRequestContext, type Dialog } from "@playwright/test";

import { login } from "./helpers";

const H = { "X-Requested-With": "fetch" };
// Archivos mínimos con firma válida: el servidor mira el contenido, no la extensión.
const JPEG = Buffer.concat([Buffer.from([0xff, 0xd8, 0xff, 0xe0]), Buffer.alloc(64)]);
const PDF = Buffer.from("%PDF-1.7\n%prueba\n");

/** Presupuesto con un ítem libre y su propuesta enviada, todo por API. Devuelve el link. */
async function sentProposal(request: APIRequestContext, suffix: string) {
  const created = await request.post("/api/v1/budgets", {
    headers: H,
    data: { currency: "ARS", title: null, event: { client_name: `Cliente ${suffix}`, name: `Fiesta ${suffix}`, event_days: 1 } },
  });
  expect(created.ok()).toBeTruthy();
  const budget = await created.json();
  const withLine = await request.post(`/api/v1/budgets/${budget.id}/draft/lines`, {
    headers: { ...H, "If-Match": String(budget.version.lock_version) },
    data: { section_id: budget.version.sections[0].id, name: "Sonido", unit_cost_amount: "1000" },
  });
  expect(withLine.ok()).toBeTruthy();
  const lock = (await withLine.json()).version.lock_version;
  const sent = await request.post(`/api/v1/budgets/${budget.id}/proposals`, {
    headers: { ...H, "If-Match": String(lock) },
    data: {},
  });
  expect(sent.ok()).toBeTruthy();
  return { budget, path: (await sent.json()).public_path as string };
}

test("el cliente acepta online y el evento queda aprobado", async ({ page, browser }, testInfo) => {
  const suffix = `${testInfo.project.name}-${Date.now()}`;
  await login(page);
  const { budget, path } = await sentProposal(page.request, suffix);

  const client = await browser.newPage();
  await client.goto(path);
  await client.getByRole("button", { name: "Aceptar propuesta" }).click();
  const form = client.getByRole("form", { name: "Aceptar propuesta" });
  await form.getByLabel("Tu nombre").fill("Ana Pérez");
  await form.getByLabel("Tu email").fill("ana@cliente.example.com");
  await form.getByRole("button", { name: "Confirmar aceptación" }).click();
  await expect(client.getByText("¡Listo! Aceptaste la propuesta.")).toBeVisible();
  // Al volver a abrir el link se ve la aceptación y ya no se puede responder.
  await client.reload();
  await expect(client.getByText(/Propuesta aceptada por Ana Pérez/)).toBeVisible();
  await expect(client.getByRole("button", { name: "Aceptar propuesta" })).toHaveCount(0);
  await client.close();

  await page.goto(`/budgets/${budget.id}`);
  const panel = page.getByRole("region", { name: "Propuestas" });
  await expect(panel).toContainText("Aceptada");
  await expect(panel).toContainText("Aceptada online por Ana Pérez (ana@cliente.example.com)");
  await page.goto(`/events/${budget.event.id}`);
  await page.getByRole("navigation", { name: "Secciones del evento" }).getByRole("link", { name: "Presupuestos" }).click();
  await expect(page.getByText("Aprobado v1")).toBeVisible();

  // Ciclo de producción desde la ficha: iniciar, realizado, cerrar y reabrir con motivo.
  await page.getByRole("navigation", { name: "Secciones del evento" }).getByRole("link", { name: "Resumen" }).click();
  await page.getByRole("button", { name: "Iniciar producción" }).click();
  // Lleva a la pestaña Producción: lista de contratación desde la baseline y tareas sugeridas.
  const hire = page.getByRole("region", { name: "Lista de contratación" });
  await expect(hire).toContainText("Sin proveedor (propio o a definir)");
  await expect(hire).toContainText("Sonido");
  await expect(hire).toContainText("Cotizado");
  await hire.getByRole("button", { name: /^Confirmar/ }).click();
  await expect(hire).toContainText("Confirmado");
  const answers = ["A-0001-00000042", "echeck 30 días"];
  const onDialog = (dialog: Dialog) => void dialog.accept(answers.shift() ?? "");
  page.on("dialog", onDialog);
  await hire.getByRole("button", { name: "Cargar factura" }).click();
  await expect(hire).toContainText("Factura A-0001-00000042 · echeck 30 días");
  page.off("dialog", onDialog);
  await hire.getByRole("button", { name: "Marcar pagado" }).click();
  await expect(hire).toContainText("Pagado");
  const tasks = page.getByRole("region", { name: "Tareas" });
  await expect(tasks).toContainText("Confirmar con el cliente los horarios de armado y desarme");
  await tasks.getByLabel("Nueva tarea").fill("Pedir planos del salón");
  await tasks.getByRole("button", { name: "Agregar" }).click();
  await tasks.getByLabel("Hecha: Pedir planos del salón").check();
  await expect(tasks.getByLabel("Hecha: Pedir planos del salón")).toBeChecked();

  // J6: gasto real en campo, vinculado a la línea, y el desvío al instante.
  await page.getByRole("navigation", { name: "Secciones del evento" }).getByRole("link", { name: "Gastos" }).click();
  await page.getByRole("button", { name: "Gasto" }).click();
  const expense = page.getByRole("form", { name: "Nuevo gasto" });
  await expense.getByLabel("Monto", { exact: true }).fill("1.452");
  await expense.getByLabel("Descripción").fill("Factura sonido");
  await expense.getByLabel("Línea del presupuesto").selectOption({ label: "Sonido" });
  await expect(expense).toContainText("Presupuestado $ 1.000,00");
  // La foto del comprobante, en el mismo paso.
  await expense.getByLabel("Comprobante (opcional)").setInputFiles({ name: "ticket-sonido.jpg", mimeType: "image/jpeg", buffer: JPEG });
  await expect(expense).toContainText("ticket-sonido.jpg");
  await expense.getByRole("button", { name: "Guardar gasto" }).click();
  // 1.452 con IVA → 1.200 de costo para un RI: 20 % arriba de lo presupuestado.
  await expect(page.getByRole("status").filter({ hasText: "Sonido:" })).toContainText(
    "Sonido: presupuestado $ 1.000,00 · real $ 1.200,00 · +20 %",
  );
  const bva = page.getByRole("region", { name: "Presupuestado vs real" });
  await expect(bva).toContainText("+20 %");
  // Algo que no estaba presupuestado va a su categoría.
  await expense.getByLabel("Monto", { exact: true }).fill("500");
  await expense.getByLabel("Descripción").fill("Hielo");
  await expense.getByLabel("Categoría").selectOption({ index: 1 });
  await expense.getByLabel("El monto incluye IVA").uncheck();
  await expense.getByRole("button", { name: "Guardar gasto" }).click();
  await expect(bva).toContainText("No presupuestado ·");
  const items = page.getByRole("region", { name: "Gastos" });
  await expect(items).toContainText("Hielo");
  // El del sonido quedó con su comprobante; al del hielo se le adjunta después (llega más tarde).
  await expect(items.getByRole("link", { name: "Comprobante" })).toHaveCount(1);
  await items.getByLabel("Adjuntar comprobante a Hielo").setInputFiles({ name: "hielo.pdf", mimeType: "application/pdf", buffer: PDF });
  await expect(items.getByRole("link", { name: "Comprobante" })).toHaveCount(2);
  const receipt = await page.request.get((await items.getByRole("link", { name: "Comprobante" }).first().getAttribute("href")) ?? "");
  expect(receipt.ok()).toBeTruthy();
  expect(["image/jpeg", "application/pdf"]).toContain(receipt.headers()["content-type"]);
  await bva.getByRole("radio", { name: "Proveedor" }).click();
  await expect(bva).toContainText("Sin proveedor");

  // O-06: rentabilidad estimada vs real, parcial hasta cerrar.
  await page.getByRole("navigation", { name: "Secciones del evento" }).getByRole("link", { name: "Rentabilidad" }).click();
  await expect(page.getByText(/^Parcial: el evento no está cerrado/)).toBeVisible();
  await expect(page.getByRole("region", { name: "Rentabilidad" })).toContainText("Margen");
  await expect(page.getByText(/Desvío de costo: \+/)).toBeVisible();

  await page.getByRole("navigation", { name: "Secciones del evento" }).getByRole("link", { name: "Resumen" }).click();
  await expect(page.getByRole("heading", { name: "Estado: En producción" })).toBeVisible();
  await page.getByRole("button", { name: "Marcar como realizado" }).click();
  await expect(page.getByRole("heading", { name: "Estado: Realizado" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Cargá los últimos gastos antes de cerrar" })).toBeVisible();
  page.once("dialog", (dialog) => void dialog.accept());
  await page.getByRole("button", { name: "Cerrar evento" }).click();
  await expect(page.getByRole("heading", { name: "Estado: Cerrado" })).toBeVisible();
  await page.getByRole("navigation", { name: "Secciones del evento" }).getByRole("link", { name: "Rentabilidad" }).click();
  await expect(page.getByText("Evento cerrado: la rentabilidad real es final.")).toBeVisible();
  await page.getByRole("navigation", { name: "Secciones del evento" }).getByRole("link", { name: "Resumen" }).click();
  await page.getByRole("button", { name: "Reabrir evento" }).click();
  await page.getByLabel("¿Por qué se reabre?").fill("Faltaba una factura");
  await page.getByRole("button", { name: "Reabrir", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Estado: Realizado" })).toBeVisible();
  await expect(page.getByText("Faltaba una factura")).toBeVisible();
});

test("el cliente rechaza y la productora aprueba otra con OC", async ({ page, browser }, testInfo) => {
  const suffix = `${testInfo.project.name}-oc-${Date.now()}`;
  await login(page);
  const { budget, path } = await sentProposal(page.request, suffix);

  const client = await browser.newPage();
  await client.goto(path);
  await client.getByRole("button", { name: "No me sirve" }).click();
  await client.getByLabel("Motivo").fill("Se pasa del presupuesto");
  await client.getByRole("button", { name: "Enviar respuesta" }).click();
  await expect(client.getByText("Registramos tu respuesta.")).toBeVisible();
  await client.close();

  await page.goto(`/budgets/${budget.id}`);
  const panel = page.getByRole("region", { name: "Propuestas" });
  await expect(panel).toContainText("“Se pasa del presupuesto”");
  await expect(panel.getByRole("button", { name: "Marcar como perdido" })).toBeVisible();

  // Nueva versión, se reenvía y el cliente confirma por mail con una OC.
  await page.getByRole("button", { name: "Nueva versión" }).click();
  // Esperar el borrador: si se genera antes, la propuesta sale sin If-Match contra un borrador nuevo.
  await expect(page.getByText("v2 · borrador")).toBeVisible();
  await page.getByRole("button", { name: "Generar propuesta" }).click();
  await page.getByRole("dialog", { name: "Generar propuesta" }).getByRole("button", { name: "Generar" }).click();
  await expect(page.getByLabel("Link de la propuesta")).toBeVisible();
  await panel.getByRole("button", { name: "Aprobar" }).click();
  const dialog = page.getByRole("dialog", { name: "Aprobar propuesta" });
  await dialog.getByLabel("N° de orden de compra (opcional)").fill("OC-4471");
  await dialog.getByLabel("OC adjunta (opcional)").setInputFiles({ name: "OC-4471.pdf", mimeType: "application/pdf", buffer: PDF });
  await expect(dialog).toContainText("OC-4471.pdf");
  await dialog.getByRole("button", { name: "Aprobar" }).click();
  await expect(panel).toContainText("OC OC-4471");
  const order = await page.request.get((await panel.getByRole("link", { name: "Ver OC" }).getAttribute("href")) ?? "");
  expect(order.ok()).toBeTruthy();
  expect(order.headers()["content-type"]).toBe("application/pdf");
  await expect(panel.getByRole("button", { name: "Marcar como perdido" })).toHaveCount(0);
});

test("el pipeline muestra el estado de cada presupuesto y filtra", async ({ page, browser }, testInfo) => {
  const suffix = `${testInfo.project.name}-pipe-${Date.now()}`;
  await login(page);
  const { path } = await sentProposal(page.request, suffix);

  await page.goto("/budgets");
  const list = page.getByRole("list", { name: "Presupuestos" });
  const row = list.getByRole("listitem").filter({ hasText: `Fiesta ${suffix}` });
  await expect(row).toContainText("Enviado");
  await page.getByRole("group", { name: "Filtrar por estado" }).getByRole("button", { name: /^Aceptado/ }).click();
  await expect(row).toHaveCount(0);

  const client = await browser.newPage();
  await client.goto(path);
  await client.getByRole("button", { name: "Aceptar propuesta" }).click();
  await client.getByLabel("Tu nombre").fill("Ana");
  await client.getByLabel("Tu email").fill("ana@cliente.example.com");
  await client.getByRole("button", { name: "Confirmar aceptación" }).click();
  await expect(client.getByText("¡Listo! Aceptaste la propuesta.")).toBeVisible();
  await client.close();

  await page.reload();
  await page.getByRole("group", { name: "Filtrar por estado" }).getByRole("button", { name: /^Aceptado/ }).click();
  await expect(list.getByRole("listitem").filter({ hasText: `Fiesta ${suffix}` })).toContainText("Aceptado");
});
