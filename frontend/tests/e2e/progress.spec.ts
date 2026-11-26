import { expect, test } from "@playwright/test";

import { CREW, login } from "./helpers";

const H = { "X-Requested-With": "fetch" };
// Alcanza la firma JPEG: el servidor mira el contenido. Es chica, así que no se achica.
const JPEG = Buffer.concat([Buffer.from([0xff, 0xd8, 0xff, 0xe0]), Buffer.alloc(64)]);

test("el taller saca una foto de avance desde Mis tareas y producción la ve en la ficha", async ({ page, browser, baseURL }, testInfo) => {
  const suffix = `${testInfo.project.name}-avance-${Date.now()}`;
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
    data: { name: `Corpóreo ${suffix}`, area: "GRAPHICS", assignee_user_id: crewId },
  });
  expect(piece.ok()).toBeTruthy();
  const pieceId = (await piece.json()).id as string;

  const { viewport, userAgent, isMobile, hasTouch } = testInfo.project.use;
  const context = await browser.newContext({ baseURL, viewport, userAgent, isMobile, hasTouch });
  const crew = await context.newPage();
  await login(crew, "/", CREW);
  const card = crew.getByRole("article", { name: `Corpóreo ${suffix}` });
  await card.getByRole("button", { name: "Foto de avance" }).click();
  const form = card.getByRole("form", { name: `Subir avance de Corpóreo ${suffix}` });
  await form.getByLabel("Foto del avance").setInputFiles({ name: "avance.jpg", mimeType: "image/jpeg", buffer: JPEG });
  await expect(form.getByRole("img", { name: "Foto elegida" })).toBeVisible();
  await form.getByLabel("Nota (opcional)").fill("Letras cortadas, mañana cableado");
  await form.getByRole("button", { name: "Enviar avance" }).click();
  await expect(form.getByText("Avance enviado.")).toBeVisible();
  await context.close();

  // Producción lo ve en la ficha de la pieza, con la foto y quién la subió.
  await page.goto(`/events/${eventId}/pieces/${pieceId}`);
  const progress = page.getByRole("region", { name: "Avances" });
  await expect(progress).toContainText("Letras cortadas, mañana cableado");
  const photo = progress.getByRole("img", { name: /Foto de avance de/ });
  await expect(photo).toBeVisible();
  const src = (await photo.getAttribute("src")) ?? "";
  const served = await page.request.get(src);
  expect(served.headers()["content-type"]).toBe("image/jpeg");

  // Y desde la ficha también se sube (solo nota).
  await progress.getByRole("button", { name: "Subir avance" }).click();
  const dialog = page.getByRole("dialog", { name: `Subir avance de Corpóreo ${suffix}` });
  await dialog.getByLabel("Nota (opcional)").fill("Revisado por producción");
  await dialog.getByRole("button", { name: "Enviar avance" }).click();
  await expect(progress).toContainText("Revisado por producción");
});
