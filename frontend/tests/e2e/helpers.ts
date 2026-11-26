import { expect, type APIRequestContext, type Page } from "@playwright/test";

/** Usuario de `make seed` (backend/scripts/seed_dev.py). */
export const OWNER = { email: "owner@demo.example.com", password: "demo-demo-1234" };

/** Taller/montaje (rol CREW), también del seed. */
export const CREW = { email: "crew@demo.example.com", password: OWNER.password };

/** Jefe/a de producción (rol PRODUCTION), también del seed. */
export const PRODUCTION = { email: "production@demo.example.com", password: OWNER.password };

export async function login(page: Page, next = "/", user = OWNER) {
  await page.goto(next);
  await expect(page).toHaveURL(/\/login/);
  await page.getByLabel("Email").fill(user.email);
  await page.getByLabel("Contraseña", { exact: true }).fill(user.password);
  await page.getByRole("button", { name: "Ingresar" }).click();
  // Esperar a que la app autenticada esté montada (no solo a que cambie la URL).
  await expect(page).not.toHaveURL(/\/login/);
  await expect(page.getByRole("button", { name: "Cerrar sesión" }).first()).toBeVisible();
}

export const H = { "X-Requested-With": "fetch" };

/** Fecha de Argentina desplazada `days` días (YYYY-MM-DD). */
export function arDate(days: number): string {
  const d = new Date(Date.now() + days * 86_400_000);
  return new Intl.DateTimeFormat("en-CA", { timeZone: "America/Argentina/Buenos_Aires" }).format(d);
}

export async function json<T>(response: Awaited<ReturnType<APIRequestContext["get"]>>): Promise<T> {
  expect(response.ok(), await response.text()).toBeTruthy();
  return (await response.json()) as T;
}

/** Evento aprobado en producción con un proveedor (con WhatsApp) y una tarea atrasada, por API. */
export async function eventInProduction(request: APIRequestContext, suffix: string) {
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
