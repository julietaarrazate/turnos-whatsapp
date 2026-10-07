import { expect, test } from "@playwright/test";

import { login } from "./helpers";

test("importar catálogo desde CSV y aplicar un aumento masivo", async ({ page }, testInfo) => {
  const suffix = `${testInfo.project.name}-${Date.now()}`;
  await login(page);
  await page.goto("/catalog");
  await page.getByRole("link", { name: "Importar" }).click();

  const csv = [
    "Producto;Categoría;Proveedor;Unidad;Costo;Incluye IVA",
    `Pantalla ${suffix};Técnica;Proveedor ${suffix};u;150.000;sí`,
    `Vallas ${suffix};Estructura;Proveedor ${suffix};kilos;100;`,
  ].join("\n");
  await page.getByLabel("Planilla del catálogo").setInputFiles({ name: "lista.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
  const previewSection = page.getByRole("region", { name: "Vista previa" });
  await expect(previewSection).toContainText("1 para importar");
  await expect(previewSection).toContainText("Unidad desconocida: kilos");
  await expect(page.getByRole("region", { name: "Columnas" }).getByLabel("Producto *")).toHaveValue("0");
  await previewSection.getByRole("button", { name: "Importar 1 filas" }).click();
  await expect(page.getByText(/Importado: 1 filas · 1 productos nuevos · 1 proveedores nuevos · 1 costos cargados/)).toBeVisible();

  await page.goto("/catalog/bulk-increase");
  await page.getByLabel("Proveedor").selectOption({ label: `Proveedor ${suffix}` });
  await page.getByLabel("Aumento (%)").fill("10");
  await page.getByRole("button", { name: "Simular" }).click();
  const simulation = page.getByRole("region", { name: "Simulación" });
  await expect(simulation).toContainText(`Pantalla ${suffix}`);
  await expect(simulation).toContainText("$ 165.000,00");
  await simulation.getByRole("button", { name: "Aplicar aumento" }).click();
  await expect(page.getByText(/Listo: 1 costos nuevos/)).toBeVisible();
});

const H = { "X-Requested-With": "fetch" };

test("armar un paquete e insertarlo en un presupuesto", async ({ page }, testInfo) => {
  const suffix = `${testInfo.project.name}-${Date.now()}`;
  await login(page);
  const categories = await (await page.request.get("/api/v1/categories", { headers: H })).json();
  const units = await (await page.request.get("/api/v1/units", { headers: H })).json();
  const product = await (
    await page.request.post("/api/v1/products", {
      headers: H,
      data: {
        name: `Tarima ${suffix}`,
        category_id: categories[0].id,
        unit_id: units.find((u: { code: string }) => u.code === "u").id,
      },
    })
  ).json();

  await page.goto("/catalog/packages");
  await page.getByRole("button", { name: "Nuevo paquete" }).click();
  const form = page.getByRole("form", { name: "Nuevo paquete" });
  await form.getByLabel("Nombre").fill(`Stand ${suffix}`);
  await form.getByRole("combobox", { name: "Agregar ítem" }).fill(`Tarima ${suffix}`);
  await page.getByRole("option", { name: new RegExp(`^Tarima ${suffix}`) }).click();
  await form.getByLabel(`Cantidad de Tarima ${suffix}`).fill("4");
  await form.getByLabel("Sección (opcional)").fill("Escenario");
  await form.getByRole("button", { name: "Guardar paquete" }).click();
  await expect(page.getByRole("region", { name: "Lista de paquetes" })).toContainText(`Stand ${suffix}`);

  await page.goto("/budgets/new");
  await page.getByLabel("Cliente").fill(`Cliente ${suffix}`);
  await page.getByLabel("Evento", { exact: true }).fill(`Feria ${suffix}`);
  await page.getByRole("button", { name: "Crear y armar el presupuesto" }).click();
  await page.getByRole("combobox", { name: "Agregar ítem" }).fill(`Stand ${suffix}`);
  await page.getByRole("option", { name: new RegExp(`Paquete: Stand ${suffix}`) }).click();
  const stage = page.getByRole("region", { name: "Sección Escenario" });
  await expect(stage.getByRole("button", { name: `Abrir Tarima ${suffix}` })).toBeVisible();
  await expect(stage.getByLabel(`Cantidad de Tarima ${suffix}`)).toHaveValue("4");
  expect(product.id).toBeTruthy();
});
