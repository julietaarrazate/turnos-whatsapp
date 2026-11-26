import { expect, test } from "@playwright/test";

import { CREW, login } from "./helpers";

const H = { "X-Requested-With": "fetch" };

test("taller: entra directo a Mis tareas, mueve su pieza con un toque y no ve nada más", async ({ page, browser, baseURL }, testInfo) => {
  const suffix = `${testInfo.project.name}-taller-${Date.now()}`;
  await login(page);
  const members = (await (await page.request.get("/api/v1/members", { headers: H })).json()) as { user_id: string; email: string }[];
  const crewId = members.find((m) => m.email === CREW.email)!.user_id;
  const created = await page.request.post("/api/v1/budgets", {
    headers: H,
    data: { currency: "ARS", title: null, event: { client_name: `Cliente ${suffix}`, name: `Stand ${suffix}`, event_days: 1 } },
  });
  expect(created.ok()).toBeTruthy();
  const eventId = (await created.json()).event.id as string;
  const piece = await page.request.post(`/api/v1/events/${eventId}/pieces`, {
    headers: H,
    data: { name: `Mostrador ${suffix}`, area: "CARPENTRY", assignee_user_id: crewId },
  });
  expect(piece.ok()).toBeTruthy();

  const { viewport, userAgent, isMobile, hasTouch } = testInfo.project.use;
  const context = await browser.newContext({ baseURL, viewport, userAgent, isMobile, hasTouch });
  const crew = await context.newPage();
  await login(crew, "/", CREW);
  await expect(crew.getByRole("heading", { name: "Mis tareas" })).toBeVisible();
  // Sin menú: ni presupuestos, ni clientes, ni el "+".
  await expect(crew.getByRole("navigation", { name: "Principal" })).toHaveCount(0);
  await expect(crew.getByRole("button", { name: "Crear" })).toHaveCount(0);

  const card = crew.getByRole("article", { name: `Mostrador ${suffix}` });
  await expect(card).toContainText(`Stand ${suffix}`);
  await expect(card).toContainText("Carpintería");
  await card.getByRole("button", { name: "En taller" }).click();
  await expect(card.getByRole("button", { name: "En taller" })).toHaveAttribute("aria-pressed", "true");

  // Producción lo ve en el evento.
  await page.goto(`/events/${eventId}/pieces`);
  await expect(page.getByRole("link", { name: new RegExp(`Mostrador ${suffix}`) })).toContainText("En taller");

  // Y si el taller intenta abrir un presupuesto, el servidor no lo deja.
  await crew.goto("/budgets");
  await expect(crew.getByText(/permiso/i).first()).toBeVisible();
  await context.close();
});
