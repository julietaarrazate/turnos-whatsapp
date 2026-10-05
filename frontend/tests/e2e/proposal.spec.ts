import { expect, test } from "@playwright/test";

import { login } from "./helpers";

const H = { "X-Requested-With": "fetch" };

test("generar propuesta y verla como el cliente, sin datos internos", async ({ page, browser }, testInfo) => {
  const suffix = `${testInfo.project.name}-${Date.now()}`;
  await login(page);
  const supplierName = `Proveedor secreto ${suffix}`;
  const categories = await (await page.request.get("/api/v1/categories", { headers: H })).json();
  const units = await (await page.request.get("/api/v1/units", { headers: H })).json();
  const supplier = await (await page.request.post("/api/v1/suppliers", { headers: H, data: { name: supplierName } })).json();
  const product = await (
    await page.request.post("/api/v1/products", {
      headers: H,
      data: {
        name: `Pantalla ${suffix}`,
        description_client: "Pantalla LED 3×2 m con operador",
        category_id: categories.find((c: { name: string }) => c.name === "Técnica (audio y video)").id,
        unit_id: units.find((u: { code: string }) => u.code === "u").id,
      },
    })
  ).json();
  await page.request.post(`/api/v1/products/${product.id}/offers`, {
    headers: H,
    data: { supplier_id: supplier.id, cost: { amount: "12345.67" } },
  });

  await page.goto("/budgets/new");
  await page.getByLabel("Cliente").fill(`Cliente ${suffix}`);
  await page.getByLabel("Evento", { exact: true }).fill(`Lanzamiento ${suffix}`);
  await page.getByRole("button", { name: "Crear y armar el presupuesto" }).click();
  await page.getByRole("combobox", { name: "Agregar ítem" }).fill(`Pantalla ${suffix}`);
  await page.getByRole("option", { name: new RegExp(`^Pantalla ${suffix}`) }).click();
  await expect(page.getByRole("region", { name: "Totales" })).toContainText("$ 16.049,37");

  await page.getByRole("button", { name: "Generar propuesta" }).click();
  const dialog = page.getByRole("dialog", { name: "Generar propuesta" });
  await dialog.getByLabel("Qué ve el cliente").selectOption("DETAILED");
  await dialog.getByLabel("Forma de pago (opcional)").fill("50 % al confirmar");
  await dialog.getByRole("button", { name: "Generar" }).click();
  const link = await page.getByLabel("Link de la propuesta").inputValue();
  expect(link).toContain("/p/");
  await expect(page.getByRole("region", { name: "Propuestas" })).toContainText("Enviada");
  await expect(page.getByText(/Versión 1 guardada/)).toBeVisible();

  // El cliente abre el link sin sesión.
  const client = await browser.newPage();
  await client.goto(link);
  await expect(client.getByRole("heading", { name: `Lanzamiento ${suffix}` })).toBeVisible();
  await expect(client.getByText("Pantalla LED 3×2 m con operador")).toBeVisible();
  await expect(client.getByRole("region", { name: "Total" })).toContainText("$ 19.419,74");
  await expect(client.getByText("50 % al confirmar")).toBeVisible();
  const html = await client.content();
  expect(html).not.toContain(supplierName);
  expect(html).not.toContain("12.345,67");
  expect(html).not.toContain("12345.67");
  await expect(client.locator('meta[name="robots"]')).toHaveAttribute("content", /noindex/);
  await client.close();

  // La productora ve que la abrieron.
  await page.reload();
  await expect(page.getByRole("region", { name: "Propuestas" })).toContainText("Vista");
});
