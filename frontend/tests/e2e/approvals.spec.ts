import { expect, test } from "@playwright/test";

import { H, json, login } from "./helpers";

test("el cliente aprueba un diseño desde el link, sin cuenta, y la productora lo ve", async ({ page, browser }, testInfo) => {
  const suffix = `${testInfo.project.name}-aprobacion-${Date.now()}`;
  await login(page);
  const budget = await json<{ event: { id: string } }>(
    await page.request.post("/api/v1/budgets", {
      headers: H,
      data: { currency: "ARS", title: null, event: { client_name: `Cliente ${suffix}`, name: `Stand ${suffix}`, event_days: 1 } },
    }),
  );
  const eventId = budget.event.id;
  await json(
    await page.request.post(`/api/v1/events/${eventId}/files`, {
      headers: H,
      data: { category: "DESIGN", title: `Render ${suffix}`, url: "https://drive.google.com/file/d/render" },
    }),
  );

  // La productora pide la aprobación desde la pestaña Archivos.
  await page.goto(`/events/${eventId}/files`);
  await page.getByRole("button", { name: `Pedir aprobación de Render ${suffix}` }).click();
  const share = page.getByRole("dialog", { name: "Link de aprobación" });
  const url = await share.getByRole("textbox", { name: "Link de aprobación" }).inputValue();
  expect(url).toMatch(/\/a\/[\w-]{20,}$/);
  await share.getByRole("button", { name: "Listo" }).click();
  await expect(page.getByText("Esperando respuesta del cliente")).toBeVisible();

  // El cliente abre el link en su teléfono, sin cuenta.
  const client = await browser.newContext();
  const phone = await client.newPage();
  await phone.goto(url);
  await expect(phone.getByRole("heading", { name: `Render ${suffix}` })).toBeVisible();
  await phone.getByRole("textbox", { name: "Tu nombre" }).fill("Laura de Natura");
  await phone.getByRole("button", { name: "Aprobado" }).click();
  await expect(phone.getByText("Aprobado por Laura de Natura")).toBeVisible();
  await client.close();

  await page.reload();
  await expect(page.getByText(/✓ Aprobado por Laura de Natura/)).toBeVisible();
});
