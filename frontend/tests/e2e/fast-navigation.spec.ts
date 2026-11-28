import { expect, test } from "@playwright/test";

import { eventInProduction, login } from "./helpers";

test("las pantallas de un evento abren sin pedirle nada al servidor de páginas", async ({ page }, testInfo) => {
  const eventId = await (async () => {
    await login(page);
    return eventInProduction(page.request, `${testInfo.project.name}-rapida-${Date.now()}`);
  })();
  await page.goto(`/events/${eventId}`);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

  // La URL real (con el ID) se mantiene y cada pestaña muestra los datos de ESE evento.
  const tabs = page.getByRole("navigation", { name: "Secciones del evento" });
  await tabs.getByRole("link", { name: "Producción" }).click();
  await expect(page).toHaveURL(new RegExp(`/events/${eventId}/production$`));
  await expect(page.getByText("Pedir planos")).toBeVisible();
  await tabs.getByRole("link", { name: "Archivos" }).click();
  await expect(page).toHaveURL(new RegExp(`/events/${eventId}/files$`));
});
