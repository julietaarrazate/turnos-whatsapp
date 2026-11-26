import { expect, test } from "@playwright/test";

import { login } from "./helpers";

test("el inicio muestra el tablero del mes, para hacer hoy y próximos eventos", async ({ page }) => {
  await login(page);
  await page.goto("/");
  const kpis = page.getByRole("region", { name: "Indicadores" });
  await expect(kpis).toContainText("Enviado");
  await expect(kpis).toContainText("Aceptado");
  await expect(kpis).toContainText("En negociación");
  await expect(kpis).toContainText("Margen prom. aceptado");
  await expect(page.getByRole("region", { name: "Para hacer hoy" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Próximos eventos" })).toBeVisible();

  // Un mes sin movimiento: enviado y aceptado en cero (en negociación es una foto de hoy).
  await page.getByLabel("Mes del tablero").fill("2020-01");
  await expect(kpis.getByText("0 presupuestos").first()).toBeVisible();
  await expect(kpis).toContainText("$ 0,00");
});

test("reporte de rentabilidad con CSV e historial del cliente", async ({ page }) => {
  await login(page);
  await page.goto("/reports");
  await expect(page.getByRole("heading", { name: "Rentabilidad" })).toBeVisible();
  await page.getByLabel("Agrupar por").selectOption("client");
  await page.getByLabel("Desde").fill("2020-01-01");
  // La base de e2e tiene eventos aprobados de otros tests (o ninguno con fecha): alcanza con que responda.
  await expect(page.getByRole("region", { name: "Rentabilidad" }).or(page.getByText("No hay eventos aprobados"))).toBeVisible();
  const [csv] = await Promise.all([page.waitForEvent("download"), page.getByRole("link", { name: "Descargar CSV" }).click()]);
  expect(csv.suggestedFilename()).toMatch(/^rentabilidad-2020-01-01-.*\.csv$/);

  await page.goto("/clients");
  await page.locator('main a[href^="/clients/"]:not([href="/clients/new"])').first().click();
  await expect(page.getByRole("region", { name: "Historial comercial" })).toContainText("Facturado histórico");
});

test("si el servidor quedó atrás en un deploy, el inicio igual carga", async ({ page }) => {
  await login(page);
  // Simula la API anterior: sin el pulso ni lo operativo de "para hacer hoy".
  await page.route("**/api/v1/dashboard?*", async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    delete body.active;
    delete body.todo.operations;
    await route.fulfill({ response, json: body });
  });
  await page.goto("/");
  await expect(page.getByRole("region", { name: "Pulso" }).getByRole("heading", { name: /Buen[oa]s/ })).toBeVisible();
  await expect(page.getByRole("region", { name: "Indicadores" })).toContainText("Enviado");
  await expect(page.getByText("No se pudo cargar esta pantalla")).toHaveCount(0);
});
