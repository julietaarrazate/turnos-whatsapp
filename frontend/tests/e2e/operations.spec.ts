import { expect, test, type APIRequestContext } from "@playwright/test";

import { login } from "./helpers";

const H = { "X-Requested-With": "fetch" };

/** Fecha de Argentina desplazada `days` días (YYYY-MM-DD). */
function arDate(days: number): string {
  const d = new Date(Date.now() + days * 86_400_000);
  return new Intl.DateTimeFormat("en-CA", { timeZone: "America/Argentina/Buenos_Aires" }).format(d);
}

async function json<T>(response: Awaited<ReturnType<APIRequestContext["get"]>>): Promise<T> {
  expect(response.ok(), await response.text()).toBeTruthy();
  return (await response.json()) as T;
}

/** Evento aprobado en producción con un proveedor (con WhatsApp) y una tarea atrasada, por API. */
async function eventInProduction(request: APIRequestContext, suffix: string) {
  const [category] = await json<{ id: string }[]>(await request.get("/api/v1/categories", { headers: H }));
  const [unit] = await json<{ id: string }[]>(await request.get("/api/v1/units", { headers: H }));
  const supplier = await json<{ id: string }>(
    await request.post("/api/v1/suppliers", {
      headers: H,
      data: { name: `Sonido ${suffix}`, contacts: [{ name: "Lucía Gómez", phone: "011 15 5555-0000", is_primary: true }] },
    }),
  );
  const product = await json<{ id: string }>(
    await request.post("/api/v1/products", { headers: H, data: { name: `Parlante ${suffix}`, category_id: category.id, unit_id: unit.id } }),
  );
  await json(await request.post(`/api/v1/products/${product.id}/offers`, { headers: H, data: { supplier_id: supplier.id, cost: { amount: "1000" } } }));

  type Budget = { id: string; event: { id: string }; version: { lock_version: number; sections: { id: string }[] } };
  const budget = await json<Budget>(
    await request.post("/api/v1/budgets", {
      headers: H,
      data: { currency: "ARS", title: null, event: { client_name: `Cliente ${suffix}`, name: `Fiesta ${suffix}`, event_days: 1 } },
    }),
  );
  const withLine = await json<{ version: { lock_version: number } }>(
    await request.post(`/api/v1/budgets/${budget.id}/draft/lines`, {
      headers: { ...H, "If-Match": String(budget.version.lock_version) },
      data: { section_id: budget.version.sections[0].id, product_id: product.id },
    }),
  );
  const sent = await json<{ proposal: { id: string } }>(
    await request.post(`/api/v1/budgets/${budget.id}/proposals`, {
      headers: { ...H, "If-Match": String(withLine.version.lock_version) },
      data: {},
    }),
  );
  await json(await request.post(`/api/v1/proposals/${sent.proposal.id}/approve`, { headers: H, data: {} }));
  const eventId = budget.event.id;
  await json(await request.patch(`/api/v1/events/${eventId}`, { headers: H, data: { start_date: arDate(3) } }));
  await json(await request.post(`/api/v1/events/${eventId}/start-production`, { headers: H }));
  await json(await request.post(`/api/v1/events/${eventId}/tasks`, { headers: H, data: { title: "Pedir planos", due_date: arDate(-1) } }));
  return eventId;
}

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
