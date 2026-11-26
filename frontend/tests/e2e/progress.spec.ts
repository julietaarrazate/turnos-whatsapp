import { expect, test } from "@playwright/test";

import { CREW, H, PRODUCTION, eventInProduction, json, login } from "./helpers";

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

test("producción: la cámara está a un toque (en el celular, el botón del medio); se saca la foto y después se elige la pieza", async ({ page, browser, baseURL }, testInfo) => {
  const suffix = `${testInfo.project.name}-camara-${Date.now()}`;
  await login(page);
  const eventId = await eventInProduction(page.request, suffix);
  const piece = await json<{ id: string }>(
    await page.request.post(`/api/v1/events/${eventId}/pieces`, { headers: H, data: { name: `Tótem ${suffix}`, area: "GRAPHICS" } }),
  );

  const { viewport, userAgent, isMobile, hasTouch } = testInfo.project.use;
  const context = await browser.newContext({ baseURL, viewport, userAgent, isMobile, hasTouch });
  const production = await context.newPage();
  await login(production, "/", PRODUCTION);
  if (isMobile) {
    // Barra de producción (como la maqueta): Inicio · Eventos · [cámara] · Actividad · Mis tareas.
    const bar = production.getByRole("navigation", { name: "Principal" }).last();
    await expect(bar.getByRole("link", { name: "Mis tareas" })).toBeVisible();
    await expect(bar.getByRole("link", { name: "Actividad" })).toBeVisible();
    await expect(bar.getByRole("link", { name: "Presupuestos" })).toHaveCount(0);
  }
  // Uno solo visible: el del medio de la barra (celular) o el del menú lateral (computadora).
  await production.getByRole("button", { name: "Foto de avance" }).click();

  const sheet = production.getByRole("dialog", { name: "Foto de avance" });
  await sheet.getByLabel("Foto del avance").setInputFiles({ name: "totem.jpg", mimeType: "image/jpeg", buffer: JPEG });
  await sheet.getByRole("radio", { name: new RegExp(`Tótem ${suffix}`) }).check();
  await sheet.getByLabel("Nota (opcional)").fill(`Impreso, falta laminar ${suffix}`);
  await sheet.getByRole("button", { name: "Enviar avance" }).click();
  await expect(production.getByRole("status").filter({ hasText: "Avance enviado" })).toBeVisible();

  // Y queda en Actividad, con la foto.
  await production.goto("/activity");
  const moves = production.getByRole("region", { name: "Movimientos" });
  await expect(moves.getByText(`subió una foto de avance de Tótem ${suffix}`)).toBeVisible();
  await expect(moves.getByText(`“Impreso, falta laminar ${suffix}”`)).toBeVisible();
  await expect(moves.getByRole("img", { name: `Foto de avance de Tótem ${suffix}` })).toBeVisible();
  await context.close();

  const updates = await json<{ note: string; has_photo: boolean }[]>(
    await page.request.get(`/api/v1/pieces/${piece.id}/updates`, { headers: H }),
  );
  expect(updates[0]).toMatchObject({ note: `Impreso, falta laminar ${suffix}`, has_photo: true });
});

test("una nota de voz se escucha en la ficha de la pieza y en Actividad", async ({ page }, testInfo) => {
  const suffix = `${testInfo.project.name}-voz-${Date.now()}`;
  await login(page);
  const eventId = await eventInProduction(page.request, suffix);
  const piece = await json<{ id: string }>(
    await page.request.post(`/api/v1/events/${eventId}/pieces`, { headers: H, data: { name: `Barra ${suffix}`, area: "METAL" } }),
  );
  // La grabación la hace el navegador con el micrófono; acá se manda una ya grabada (firma WebM).
  const webm = Buffer.concat([Buffer.from([0x1a, 0x45, 0xdf, 0xa3]), Buffer.alloc(200)]);
  const update = await json<{ id: string; has_audio: boolean }>(
    await page.request.post(`/api/v1/pieces/${piece.id}/updates`, {
      headers: H,
      data: { audio: { filename: "nota.webm", file_base64: webm.toString("base64") } },
    }),
  );
  expect(update.has_audio).toBe(true);

  await page.goto(`/events/${eventId}/pieces/${piece.id}`);
  const voice = page.getByRole("region", { name: "Avances" }).getByLabel(/Nota de voz de/);
  await expect(voice).toBeVisible();
  const served = await page.request.get((await voice.getAttribute("src")) ?? "");
  expect(served.headers()["content-type"]).toBe("audio/webm");

  await page.goto("/activity");
  await expect(page.getByRole("region", { name: "Movimientos" }).getByText(`dejó una nota de voz en Barra ${suffix}`)).toBeVisible();
});

test("la campanita avisa lo que hicieron otros y se apaga al abrir Actividad", async ({ page, browser, baseURL }, testInfo) => {
  const suffix = `${testInfo.project.name}-campana-${Date.now()}`;
  await login(page);
  const eventId = await eventInProduction(page.request, suffix);
  const piece = await json<{ id: string }>(
    await page.request.post(`/api/v1/events/${eventId}/pieces`, { headers: H, data: { name: `Atril ${suffix}`, area: "CARPENTRY" } }),
  );
  // Al abrir Actividad queda todo visto.
  await page.goto("/activity");
  const bell = page.getByRole("link", { name: /^Novedades:/ }).first();
  await expect(bell).toHaveAccessibleName("Novedades: ninguna nueva");

  // Producción mueve la pieza desde su teléfono.
  const { viewport, userAgent, isMobile, hasTouch } = testInfo.project.use;
  const context = await browser.newContext({ baseURL, viewport, userAgent, isMobile, hasTouch });
  const production = await context.newPage();
  await login(production, "/", PRODUCTION);
  await json(await production.request.patch(`/api/v1/pieces/${piece.id}`, { headers: H, data: { status: "IN_WORKSHOP" } }));
  await context.close();

  // En cualquier pantalla la campanita trae lo nuevo (y se refresca sola cada 15 s).
  await page.goto("/");
  await expect(bell).toHaveAccessibleName(/Novedades: \d+ nuevas?$/, { timeout: 20_000 });
  await bell.click();
  await expect(page).toHaveURL(/\/activity$/);
  const item = page.getByRole("listitem").filter({ hasText: `pasó Atril ${suffix} a En taller` });
  await expect(item).toContainText("Nuevo");
  await expect(bell).toHaveAccessibleName("Novedades: ninguna nueva");
});
