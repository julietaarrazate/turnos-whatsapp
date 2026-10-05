import { expect, test } from "@playwright/test";

import { login } from "./helpers";

test("proveedor, producto, oferta con costo e historial", async ({ page }) => {
  const suffix = `${Date.now()}`;
  const supplier = `Rental ${suffix}`;
  const product = `Truss 3 m ${suffix}`;

  await login(page, "/suppliers/new");
  await page.getByLabel("Nombre", { exact: true }).fill(supplier);
  await page.getByRole("checkbox", { name: "Estructura" }).check();
  await page.getByRole("button", { name: "Crear proveedor" }).click();
  await expect(page.getByRole("heading", { name: supplier })).toBeVisible();

  await page.goto("/catalog/new");
  await page.getByLabel("Nombre", { exact: true }).fill(product);
  await page.getByLabel("Rubro").selectOption({ label: "Estructura" });
  await page.getByLabel("Modo de cobro").selectOption("PER_DAY");
  await page.getByRole("button", { name: "Crear producto" }).click();
  await expect(page.getByRole("heading", { name: product })).toBeVisible();

  // Primera oferta con costo en formato argentino.
  await page.getByRole("button", { name: "Agregar proveedor" }).click();
  const addForm = page.getByRole("form", { name: "Agregar proveedor" });
  await addForm.getByLabel("Proveedor", { exact: true }).selectOption({ label: supplier });
  await addForm.getByLabel("Costo", { exact: true }).fill("150.000");
  await expect(addForm.getByText("Se guarda como $ 150.000,00")).toBeVisible();
  await addForm.getByRole("button", { name: "Agregar" }).click();
  await expect(addForm).toBeHidden();
  await expect(page.getByText("$ 150.000,00", { exact: true })).toBeVisible();
  await expect(page.getByText("Preferido", { exact: true })).toBeVisible();

  // Un costo nuevo reemplaza al vigente y queda en el historial.
  await page.getByRole("button", { name: "Cargar costo" }).click();
  const costForm = page.getByRole("form", { name: `Nuevo costo de ${supplier}` });
  await costForm.getByLabel("Costo", { exact: true }).fill("162.500,50");
  await costForm.getByRole("button", { name: "Guardar costo" }).click();
  await expect(costForm).toBeHidden();
  const history = page.getByRole("list", { name: "Historial de costos" });
  await expect(history.getByRole("listitem")).toHaveCount(2);
  await expect(history.getByRole("listitem").first()).toContainText("$ 162.500,50");
  await expect(history.getByRole("listitem").last()).toContainText("$ 150.000,00");

  // El catálogo lo muestra con su proveedor preferido.
  await page.goto("/catalog");
  await page.getByRole("searchbox", { name: "Buscar producto" }).fill(suffix);
  await expect(page.getByRole("link", { name: new RegExp(product) })).toContainText(supplier);
});

test("alta y edición de un cliente", async ({ page }) => {
  const name = `Banco ${Date.now()}`;
  await login(page, "/clients/new");
  await page.getByLabel("Nombre", { exact: true }).fill(name);
  await page.getByLabel("CUIT").fill("30-71234567-1");
  await page.getByRole("button", { name: "Agregar contacto" }).click();
  await page.getByLabel("Nombre", { exact: true }).nth(1).fill("Ana Pérez");
  await page.getByRole("button", { name: "Crear cliente" }).click();
  await expect(page.getByRole("heading", { name })).toBeVisible();

  await page.getByLabel("Ciudad").fill("Rosario");
  await page.getByRole("button", { name: "Guardar cambios" }).click();
  await expect(page.getByText("Cambios guardados.")).toBeVisible();

  await page.goto("/clients");
  await page.getByRole("searchbox", { name: "Buscar por nombre o CUIT" }).fill(name);
  await expect(page.getByRole("link", { name: new RegExp(name) })).toContainText("Ana Pérez · Rosario");
});
