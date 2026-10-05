import { expect, type Page, test } from "@playwright/test";

import { login } from "./helpers";

const H = { "X-Requested-With": "fetch" };

/** Un producto propio de esta corrida, con proveedor y costo, creado por la API. */
async function seedProduct(page: Page, suffix: string) {
  const categories = await (await page.request.get("/api/v1/categories", { headers: H })).json();
  const units = await (await page.request.get("/api/v1/units", { headers: H })).json();
  const estructura = categories.find((c: { name: string }) => c.name === "Estructura");
  const unit = units.find((u: { code: string }) => u.code === "u");
  const supplier = await (
    await page.request.post("/api/v1/suppliers", { headers: H, data: { name: `Rental ${suffix}` } })
  ).json();
  const created = await page.request.post("/api/v1/products", {
    headers: H,
    data: { name: `Truss ${suffix}`, category_id: estructura.id, unit_id: unit.id, charge_mode: "PER_DAY" },
  });
  expect(created.status(), await created.text()).toBe(201);
  const product = await created.json();
  const offer = await page.request.post(`/api/v1/products/${product.id}/offers`, {
    headers: H,
    data: { supplier_id: supplier.id, cost: { amount: "10000" } },
  });
  expect(offer.status(), await offer.text()).toBe(201);
  return product.name as string;
}

async function offerOf(page: Page, productName: string): Promise<string> {
  const list = await (await page.request.get(`/api/v1/products?q=${encodeURIComponent(productName)}`, { headers: H })).json();
  const detail = await (await page.request.get(`/api/v1/products/${list.items[0].id}`, { headers: H })).json();
  return detail.offers[0].id as string;
}

async function newBudgetWith(page: Page, suffix: string, productName: string) {
  await page.goto("/budgets/new");
  await page.getByLabel("Cliente").fill(`Cliente ${suffix}`);
  await page.getByLabel("Evento", { exact: true }).fill(`Evento ${suffix}`);
  await page.getByRole("button", { name: "Crear y armar el presupuesto" }).click();
  await expect(page.getByRole("heading", { name: new RegExp(`Evento ${suffix}`) })).toBeVisible();
  await page.getByRole("combobox", { name: "Agregar ítem" }).fill(productName);
  await page.getByRole("option", { name: new RegExp(`^${productName}`) }).click();
}

test("J2: nuevo presupuesto, ítems del catálogo y libres, precio objetivo y guardar versión", async ({ page }, testInfo) => {
  const suffix = `${testInfo.project.name}-${Date.now()}`;
  await login(page);
  const productName = await seedProduct(page, suffix);

  // B-01: cliente nuevo → evento (2 días) → editor.
  await page.goto("/budgets/new");
  await page.getByLabel("Cliente").fill(`Cliente ${suffix}`);
  await page.getByLabel("Evento", { exact: true }).fill(`Convención ${suffix}`);
  await page.getByLabel("Días de evento").fill("2");
  await page.getByRole("button", { name: "Crear y armar el presupuesto" }).click();
  await expect(page.getByRole("heading", { name: new RegExp(`Convención ${suffix}`) })).toBeVisible();
  await expect(page.getByText("Presupuestando")).toBeVisible();

  // Ítem del catálogo: cobra por día, toma los 2 días del evento y el costo vigente.
  const search = page.getByRole("combobox", { name: "Agregar ítem" });
  await search.fill(productName);
  // La opción del catálogo (no la de "Ítem libre", que también lleva el texto buscado).
  await page.getByRole("option", { name: new RegExp(`^${productName}`) }).click();
  const footer = page.getByRole("region", { name: "Totales" });
  // 10.000 × 1 × 2 días = 20.000 de costo; markup general 30 % → 26.000.
  await expect(footer).toContainText("$ 26.000,00");

  // Cambiar la cantidad recalcula en el servidor.
  await page.getByLabel(`Cantidad de ${productName}`).fill("3");
  await page.getByLabel(`Cantidad de ${productName}`).press("Enter");
  await expect(footer).toContainText("$ 78.000,00");

  // Ítem libre con costo cargado en el panel de detalle.
  await search.fill("Flete");
  await page.getByRole("option", { name: /Ítem libre/ }).click();
  await page.getByRole("button", { name: "Abrir Flete" }).click();
  const detail = page.getByRole("dialog", { name: "Detalle de Flete" });
  await detail.getByLabel("Costo unitario").fill("50.000");
  await detail.getByLabel("Costo unitario").press("Enter");
  await expect(detail).toContainText("$ 65.000,00");
  await detail.getByRole("button", { name: "Cerrar" }).click();
  await expect(footer).toContainText("$ 143.000,00");

  // Precio objetivo: el cliente tiene $ 150.000 (sin IVA).
  await page.getByRole("button", { name: /Cálculo del precio/ }).click();
  await page.getByLabel("Modo").selectOption("PRICE");
  const target = page.getByLabel("Precio objetivo (sin IVA)");
  await target.fill("150.000");
  await target.press("Enter");
  await expect(footer).toContainText("$ 150.000,00");

  // Guardar versión: queda congelada y se puede abrir una nueva.
  await page.getByRole("button", { name: "Guardar versión" }).click();
  await page.getByLabel("Nota de la versión").fill("Primera propuesta");
  await page.getByRole("button", { name: "Guardar v1" }).click();
  await expect(page.getByText(/Versión 1 guardada: Primera propuesta/)).toBeVisible();
  await page.getByRole("button", { name: "Nueva versión" }).click();
  await expect(page.getByText("v2 · borrador")).toBeVisible();
  await expect(footer).toContainText("$ 150.000,00");
});

test("costos más nuevos, re-aplicar reglas y duplicar para otro evento", async ({ page }, testInfo) => {
  const suffix = `${testInfo.project.name}-${Date.now()}`;
  await login(page);
  const productName = await seedProduct(page, suffix);
  await newBudgetWith(page, suffix, productName);
  const footer = page.getByRole("region", { name: "Totales" });
  await expect(footer).toContainText("$ 13.000,00"); // 10.000 × 1 día × 1,30
  const budgetUrl = page.url();

  // Aumenta el proveedor: el editor avisa y deja actualizar con vista previa.
  const offerId = await offerOf(page, productName);
  const raised = await page.request.post(`/api/v1/offers/${offerId}/prices`, { headers: H, data: { amount: "12000" } });
  expect(raised.status()).toBe(201);
  await page.reload();
  await expect(page.getByText("Hay 1 costo más nuevo en el catálogo.")).toBeVisible();
  await page.getByRole("button", { name: "Revisar y actualizar" }).click();
  const dialog = page.getByRole("dialog", { name: "Actualizar costos" });
  await expect(dialog).toContainText("$ 10.000,00 → $ 12.000,00");
  await dialog.getByRole("button", { name: "Actualizar 1 costo" }).click();
  await expect(footer).toContainText("$ 15.600,00");
  await expect(page.getByText("Hay 1 costo más nuevo en el catálogo.")).toBeHidden();

  // Re-aplicar reglas: sin cambios en las reglas, no hay nada que aplicar.
  await page.getByRole("button", { name: "Re-aplicar reglas" }).click();
  const rules = page.getByRole("dialog", { name: "Re-aplicar reglas de pricing" });
  await expect(rules.getByRole("button", { name: "Aplicar" })).toBeVisible();
  await rules.getByRole("button", { name: "Cerrar" }).click();

  // Duplicar para otro evento: nuevo cliente, mismos ítems, aviso de lo que cambió.
  await page.getByRole("link", { name: "Duplicar para otro evento" }).click();
  await expect(page.getByRole("heading", { name: "Duplicar presupuesto" })).toBeVisible();
  await page.getByLabel("Cliente").fill(`Otro ${suffix}`);
  await page.getByLabel("Evento", { exact: true }).fill(`Gira ${suffix}`);
  await page.getByRole("button", { name: "Duplicar" }).click();
  await expect(page.getByRole("heading", { name: new RegExp(`Evento ${suffix}`) })).toBeVisible();
  await expect(page.getByText(/Presupuesto duplicado con los valores de hoy/)).toBeVisible();
  await expect(footer).toContainText("$ 15.600,00");
  expect(page.url()).not.toBe(budgetUrl);
});
