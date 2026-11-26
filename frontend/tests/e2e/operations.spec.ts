import { expect, test } from "@playwright/test";

import { H, arDate, eventInProduction, json, login } from "./helpers";

test("para hacer hoy muestra lo operativo y desde ahí se le escribe al proveedor por WhatsApp", async ({ page }, testInfo) => {
  const suffix = `${testInfo.project.name}-ops-${Date.now()}`;
  await login(page);
  const eventId = await eventInProduction(page.request, suffix);

  await page.goto("/");
  const todo = page.getByRole("region", { name: "Para hacer hoy" });
  await expect(todo.getByRole("link", { name: new RegExp(`1 tarea atrasada · #\\d+ Fiesta ${suffix}`) })).toBeVisible();
  const toConfirm = todo.getByRole("link", { name: new RegExp(`1 proveedor sin confirmar · #\\d+ Fiesta ${suffix}`) });
  await toConfirm.click();
  await expect(page).toHaveURL(new RegExp(`/events/${eventId}/production$`));

  const list = page.getByRole("region", { name: "Lista de contratación" });
  await expect(list).toContainText("Contacto: Lucía Gómez · 011 15 5555-0000");
  const whatsapp = list.getByRole("link", { name: `WhatsApp a Sonido ${suffix}: Pedir confirmación` });
  const href = (await whatsapp.getAttribute("href")) ?? "";
  expect(href.startsWith("https://wa.me/5491155550000?text=")).toBe(true);
  const text = decodeURIComponent(href.split("?text=")[1]);
  expect(text).toContain(`Hola Lucía! Te escribo de`);
  expect(text).toContain(`por Fiesta ${suffix} el `);
  expect(text).toContain(`¿Me confirmás Parlante ${suffix}?`);

  // Al confirmarlo, el mensaje pasa a ser un recordatorio y sale de "para hacer hoy".
  await list.getByRole("button", { name: `Confirmar Sonido ${suffix}` }).click();
  await expect(list.getByRole("link", { name: `WhatsApp a Sonido ${suffix}: Recordatorio` })).toBeVisible();
  await page.goto("/");
  await expect(todo.getByRole("link", { name: new RegExp(`proveedor sin confirmar · #\\d+ Fiesta ${suffix}`) })).toHaveCount(0);
});

test("el inicio muestra el pulso: cada evento activo con el avance de sus piezas y sus atrasos", async ({ page }, testInfo) => {
  const suffix = `${testInfo.project.name}-pulso-${Date.now()}`;
  await login(page);
  const eventId = await eventInProduction(page.request, suffix); // trae una tarea vencida
  // El montaje más cercano va primero en el pulso: mañana, para no depender de otros eventos.
  await json(await page.request.patch(`/api/v1/events/${eventId}`, { headers: H, data: { start_date: arDate(1) } }));
  for (const [name, status] of [["Mostrador", "MOUNTED"], ["Tótem", "IN_WORKSHOP"]] as const) {
    const piece = await json<{ id: string }>(await page.request.post(`/api/v1/events/${eventId}/pieces`, { headers: H, data: { name } }));
    await json(await page.request.patch(`/api/v1/pieces/${piece.id}`, { headers: H, data: { status } }));
  }

  await page.goto("/");
  const pulse = page.getByRole("region", { name: "Pulso" });
  await expect(pulse.getByRole("heading", { name: /Buen[oa]s/ })).toBeVisible();
  await expect(pulse).toContainText("eventos activos");
  const card = page.getByRole("region", { name: "Eventos activos" }).getByRole("link", { name: new RegExp(`Fiesta ${suffix}`) });
  // Montado 100 % y taller 50 % → 75 %; una de dos lista; la tarea vencida es un atraso.
  await expect(card).toContainText("75%");
  await expect(card).toContainText("1 de 2 piezas");
  await expect(card).toContainText("1 atraso");
  await expect(card).toContainText("Montaje");
  await card.click();
  await expect(page).toHaveURL(new RegExp(`/events/${eventId}/pieces$`));
});
