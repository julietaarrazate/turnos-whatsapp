import path from "node:path";

import { expect, test } from "@playwright/test";

import { login } from "./helpers";

// Planilla sintética con el formato de la productora piloto (backend/tests/budgets/test_sheet_import.py).
const SHEET = path.join(__dirname, "fixtures", "planilla-demo.xlsx");

test("importar un presupuesto desde la planilla de la productora", async ({ page }, testInfo) => {
  const suffix = `${testInfo.project.name}-${Date.now()}`;
  await login(page);
  await page.goto("/budgets/new");
  await page.getByLabel("Cliente").fill(`Cliente planilla ${suffix}`);

  await page.getByLabel("Planilla de presupuesto (.xlsx)").setInputFiles(SHEET);
  const panel = page.getByRole("region", { name: "Importar desde una planilla" });
  await expect(panel).toContainText("hoja «Feria demo»: 6 ítems en 3 rubros");
  await expect(panel).toContainText("fee de gestión 5 %");
  // Avisa que la fila SUBTOTAL de la planilla deja afuera ítems.
  await expect(panel).toContainText("SUBTOTAL de la planilla dice $ 10.500,00 pero los ítems suman $ 14.000,00");
  await expect(panel).toContainText("Válido por 7 días.");
  // El nombre del evento sale de la planilla.
  await expect(page.getByLabel("Evento", { exact: true })).toHaveValue("FERIA DEMO");
  await page.getByLabel("Evento", { exact: true }).fill(`Feria ${suffix}`);

  // Otra hoja del mismo libro.
  await panel.getByLabel("Hoja").selectOption("Otro evento");
  await expect(panel).toContainText("hoja «Otro evento»: 1 ítems en 1 rubros");
  await panel.getByLabel("Hoja").selectOption("Feria demo");
  await expect(panel).toContainText("hoja «Feria demo»");

  await page.getByRole("button", { name: "Crear con la planilla" }).click();
  await expect(page.getByRole("heading", { name: new RegExp(`Feria ${suffix}`) })).toBeVisible();
  const footer = page.getByRole("region", { name: "Totales" });
  // 14.000 de ítems + 700 de fee (5 %).
  await expect(footer).toContainText("$ 14.700,00");
  await expect(footer).toContainText("fee de gestión (5 %): $ 700,00");
  // Los rubros de la planilla son las secciones; cada ítem con el precio de la planilla.
  const stage = page.getByRole("region", { name: "Sección ESCENARIO" });
  await expect(stage.getByRole("button", { name: "Abrir Vallas x 10" })).toBeVisible();
  await expect(stage).toContainText("$ 10.000,00");
});
