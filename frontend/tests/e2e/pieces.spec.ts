import { expect, test } from "@playwright/test";

import { login } from "./helpers";

const H = { "X-Requested-With": "fetch" };

test("piezas: cargar, cambiar de fase con un toque y ver el avance", async ({ page }, testInfo) => {
  const suffix = `${testInfo.project.name}-piezas-${Date.now()}`;
  await login(page);
  const created = await page.request.post("/api/v1/budgets", {
    headers: H,
    data: { currency: "ARS", title: null, event: { client_name: `Cliente ${suffix}`, name: `Stand ${suffix}`, event_days: 1 } },
  });
  expect(created.ok()).toBeTruthy();
  const eventId = (await created.json()).event.id as string;

  await page.goto(`/events/${eventId}`);
  await page.getByRole("navigation", { name: "Secciones del evento" }).getByRole("link", { name: "Piezas" }).click();
  await expect(page).toHaveURL(new RegExp(`/events/${eventId}/pieces$`));
  await expect(page.getByText("Todavía no hay piezas")).toBeVisible();

  const form = page.getByRole("form", { name: "Agregar pieza" });
  await form.getByLabel("Nombre de la pieza").fill("Mostrador recepción");
  await form.getByLabel("Área").selectOption("CARPENTRY");
  await form.getByRole("button", { name: "Agregar" }).click();
  // Se escribe la siguiente sin esperar a que se guarde la anterior: no se tiene que perder.
  await form.getByLabel("Nombre de la pieza").fill("Corpóreo LED");
  await form.getByLabel("Área").selectOption("GRAPHICS");
  await form.getByRole("button", { name: "Agregar" }).click();

  const carpentry = page.getByRole("region", { name: "Carpintería" });
  await expect(carpentry.getByRole("link", { name: /Mostrador recepción/ })).toContainText("Pend. diseño");
  await expect(page.getByRole("region", { name: "Avance de las piezas" })).toContainText("0 de 2 listas");

  // La ficha: la fase se cambia con un toque.
  await carpentry.getByRole("link", { name: /Mostrador recepción/ }).click();
  const status = page.getByRole("region", { name: "Estado de la pieza" });
  await status.getByRole("button", { name: "Montado" }).click();
  await expect(status.getByRole("button", { name: "Montado" })).toHaveAttribute("aria-pressed", "true");
  await expect(status).toContainText("En predio / montado");

  await page.getByRole("link", { name: "Piezas", exact: true }).first().click();
  await expect(carpentry.getByRole("link", { name: /Mostrador recepción/ })).toContainText("Montado");
  // Montado 100 % y diseño 0 % → 50 %; una de dos lista.
  const progress = page.getByRole("region", { name: "Avance de las piezas" });
  await expect(progress).toContainText("1 de 2 listas");
  await expect(progress).toContainText("50%");

  // Filtrar por área.
  await page.getByRole("group", { name: "Filtrar por área" }).getByRole("button", { name: "Gráfica y corpóreos" }).click();
  await expect(page.getByRole("region", { name: "Carpintería" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: /Corpóreo LED/ })).toBeVisible();
});
