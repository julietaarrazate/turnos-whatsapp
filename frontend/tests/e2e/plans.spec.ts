import { expect, test } from "@playwright/test";

import { CREW, H, json, login } from "./helpers";

const PDF_V1 = Buffer.from("%PDF-1.4\n%plano v1\n");
const PDF_V2 = Buffer.from("%PDF-1.4\n%plano v2 con medidas nuevas\n");

test("planos: el mismo título sube como versión nueva y el taller ve la vigente", async ({ page, browser, baseURL }, testInfo) => {
  const suffix = `${testInfo.project.name}-planos-${Date.now()}`;
  await login(page);
  const members = await json<{ user_id: string; email: string }[]>(await page.request.get("/api/v1/members", { headers: H }));
  const crewId = members.find((m) => m.email === CREW.email)!.user_id;
  const budget = await json<{ event: { id: string } }>(
    await page.request.post("/api/v1/budgets", {
      headers: H,
      data: { currency: "ARS", title: null, event: { client_name: `Cliente ${suffix}`, name: `Stand ${suffix}`, event_days: 1 } },
    }),
  );
  const eventId = budget.event.id;
  const piece = await json<{ id: string }>(
    await page.request.post(`/api/v1/events/${eventId}/pieces`, {
      headers: H,
      data: { name: `Mostrador ${suffix}`, area: "CARPENTRY", assignee_user_id: crewId },
    }),
  );

  await page.goto(`/events/${eventId}/pieces/${piece.id}`);
  const plans = page.getByRole("region", { name: "Planos y archivos" });
  await expect(plans).toContainText("Todavía no hay planos.");
  await plans.getByLabel("Título del plano").fill("Plano de corte");
  await plans.getByLabel("Archivo del plano").setInputFiles({ name: "corte.pdf", mimeType: "application/pdf", buffer: PDF_V1 });
  await expect(plans.getByRole("link", { name: /Plano de corte.*v1 vigente/ })).toBeVisible();

  await plans.getByLabel("Título del plano").fill("Plano de corte");
  await plans.getByLabel("Archivo del plano").setInputFiles({ name: "corte-v2.pdf", mimeType: "application/pdf", buffer: PDF_V2 });
  await expect(plans.getByRole("link", { name: /Plano de corte.*v2 vigente/ })).toBeVisible();
  await expect(plans.getByText("Versiones anteriores (1)")).toBeVisible();

  const { viewport, userAgent, isMobile, hasTouch } = testInfo.project.use;
  const context = await browser.newContext({ baseURL, viewport, userAgent, isMobile, hasTouch });
  const crew = await context.newPage();
  await login(crew, "/", CREW);
  const card = crew.getByRole("article", { name: `Mostrador ${suffix}` });
  const link = card.getByRole("link", { name: /Ver plano de corte/ });
  await expect(link).toContainText("v2");
  const served = await crew.request.get((await link.getAttribute("href")) ?? "");
  expect(served.headers()["content-type"]).toBe("application/pdf");
  expect((await served.body()).toString()).toContain("plano v2");
  await context.close();
});
