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
