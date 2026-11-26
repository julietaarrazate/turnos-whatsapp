import { expect, test } from "@playwright/test";

import { H, json, login } from "./helpers";

const PDF = Buffer.from("%PDF-1.4\n%manual de marca\n");

test("archivos del evento: link de Drive, PDF del cliente, planos solos y el buscador", async ({ page }, testInfo) => {
  const suffix = `${testInfo.project.name}-archivos-${Date.now()}`;
  await login(page);
  const budget = await json<{ event: { id: string } }>(
    await page.request.post("/api/v1/budgets", {
      headers: H,
      data: { currency: "ARS", title: null, event: { client_name: `Cliente ${suffix}`, name: `Expo ${suffix}`, event_days: 1 } },
    }),
  );
  const eventId = budget.event.id;
  const piece = await json<{ id: string }>(
    await page.request.post(`/api/v1/events/${eventId}/pieces`, { headers: H, data: { name: `Mostrador ${suffix}` } }),
  );
  await page.request.post(`/api/v1/pieces/${piece.id}/plans`, {
    headers: H,
    data: { title: "Plano de corte", filename: "p.pdf", file_base64: PDF.toString("base64") },
  });

  await page.goto(`/events/${eventId}`);
  await page.getByRole("navigation", { name: "Secciones del evento" }).getByRole("link", { name: "Archivos" }).click();
  await expect(page).toHaveURL(new RegExp(`/events/${eventId}/files$`));
  // El plano de la pieza ya está, sin cargarlo dos veces.
  await expect(page.getByRole("region", { name: "Diseño" })).toContainText("Plano de corte");

  await page.getByRole("button", { name: "Agregar archivo o link" }).click();
  const form = page.getByRole("form", { name: "Agregar archivo" });
  await form.getByRole("button", { name: "Pegar link (Drive…)" }).click();
  await form.getByLabel("Tipo", { exact: true }).selectOption("DESIGN");
  await form.getByLabel("Pieza (opcional)").selectOption({ label: `Mostrador ${suffix}` });
  await form.getByLabel("Nombre", { exact: true }).fill(`Render ${suffix}`);
  await form.getByLabel("Link", { exact: true }).fill("https://drive.google.com/file/d/render-ejemplo");
  await form.getByRole("button", { name: "Agregar" }).click();
  const design = page.getByRole("region", { name: "Diseño" });
  const render = design.getByRole("link", { name: new RegExp(`Render ${suffix}`) });
  await expect(render).toHaveAttribute("href", "https://drive.google.com/file/d/render-ejemplo");
  await expect(render).toContainText(`Mostrador ${suffix}`);

  await form.getByRole("button", { name: "Subir archivo" }).click();
  await form.getByLabel("Tipo", { exact: true }).selectOption("CLIENT");
  await form.getByLabel("Pieza (opcional)").selectOption("");
  await form.getByLabel("Nombre", { exact: true }).fill(`Manual de marca ${suffix}`);
  await form.getByLabel("Archivo", { exact: true }).setInputFiles({ name: "manual.pdf", mimeType: "application/pdf", buffer: PDF });
  await form.getByRole("button", { name: "Agregar" }).click();
  const client = page.getByRole("region", { name: "Del cliente" });
  const manual = client.getByRole("link", { name: new RegExp(`Manual de marca ${suffix}`) });
  await expect(manual).toBeVisible();
  const served = await page.request.get((await manual.getAttribute("href")) ?? "");
  expect(served.headers()["content-type"]).toBe("application/pdf");

  // Buscador: en todos los eventos.
  await page.goto("/files");
  await page.getByLabel("Buscar archivos").fill(`manual ${suffix}`);
  const results = page.getByRole("region", { name: "Resultados" });
  await expect(results.getByRole("link", { name: `Manual de marca ${suffix}` })).toBeVisible();
  await expect(results).toContainText(`Expo ${suffix}`);
});
