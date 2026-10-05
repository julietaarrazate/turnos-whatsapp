import { expect, test, type APIRequestContext } from "@playwright/test";

import { login } from "./helpers";

const H = { "X-Requested-With": "fetch" };

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
  await expect(page.getByText("Aprobado v1")).toBeVisible();
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
  await page.getByRole("button", { name: "Generar propuesta" }).click();
  await page.getByRole("dialog", { name: "Generar propuesta" }).getByRole("button", { name: "Generar" }).click();
  await expect(page.getByLabel("Link de la propuesta")).toBeVisible();
  await panel.getByRole("button", { name: "Aprobar" }).click();
  const dialog = page.getByRole("dialog", { name: "Aprobar propuesta" });
  await dialog.getByLabel("N° de orden de compra (opcional)").fill("OC-4471");
  await dialog.getByRole("button", { name: "Aprobar" }).click();
  await expect(panel).toContainText("OC OC-4471");
  await expect(panel.getByRole("button", { name: "Marcar como perdido" })).toHaveCount(0);
});
