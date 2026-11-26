import { expect, test } from "@playwright/test";

import { login } from "./helpers";

test("configurar markups, cargos y tipo de cambio, y ver el markup en el producto", async ({ page }) => {
  const suffix = `${Date.now()}`;
  const category = `Gráfica ${suffix}`;
  await login(page);
  // Un rubro propio de esta corrida (la base de e2e se comparte entre corridas y proyectos).
  const created = await page.request.post("/api/v1/categories", {
    data: { name: category },
    headers: { "X-Requested-With": "fetch" },
  });
  expect(created.status()).toBe(201);
  await page.goto("/settings/pricing");
  await expect(page.getByRole("heading", { name: "Precios", exact: true })).toBeVisible();

  // Markup del rubro: 40 %.
  const row = page.getByRole("listitem").filter({ has: page.getByLabel(`Markup de ${category}`) });
  await expect(row).toContainText("Usa el general");
  await row.getByLabel(`Markup de ${category}`).fill("40");
  await row.getByRole("button", { name: "Guardar" }).click();
  await expect(row).toContainText("40 %");

  // Un cargo sobre la venta.
  const chargeForm = page.getByRole("form", { name: "Agregar cargo" });
  await chargeForm.getByLabel("Cargo").fill(`Comisión ${suffix}`);
  await chargeForm.getByLabel("Alícuota").fill("3,5");
  await chargeForm.getByRole("button", { name: "Agregar" }).click();
  await expect(page.getByText(`Comisión ${suffix}`)).toBeVisible();
  await expect(page.getByRole("listitem").filter({ hasText: `Comisión ${suffix}` })).toContainText(
    "3,5 % de la venta neta",
  );

  // Tipo de cambio.
  const fxForm = page.getByRole("form", { name: "Cargar tipo de cambio" });
  await fxForm.getByLabel("Pesos por dólar").fill("1.450,50");
  await fxForm.getByRole("button", { name: "Guardar" }).click();
  await expect(page.getByText("US$ 1 = $ 1.450,50")).toBeVisible();

  // Un producto de Gráfica toma el markup del rubro.
  await page.goto("/catalog/new");
  await page.getByLabel("Nombre", { exact: true }).fill(`Banner ${suffix}`);
  await page.getByLabel("Rubro").selectOption({ label: category });
  await page.getByRole("button", { name: "Crear producto" }).click();
  await expect(page.getByText(`Al presupuestar toma 40 % · rubro ${category}.`)).toBeVisible();

  // Y con un markup propio, toma el del producto.
  const own = page.getByRole("form", { name: "Markup propio" });
  await own.getByLabel("Markup propio").fill("55");
  await own.getByRole("button", { name: "Guardar" }).click();
  await expect(page.getByText(`Al presupuestar toma 55 % · producto Banner ${suffix}.`)).toBeVisible();
});
