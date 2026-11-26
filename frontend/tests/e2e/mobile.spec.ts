import { expect, test } from "@playwright/test";

import { login } from "./helpers";

test("en el celular hay barra inferior y acciones rápidas", async ({ page, isMobile }) => {
  test.skip(!isMobile, "solo viewport mobile");
  await login(page);
  const bottomNav = page.getByRole("navigation", { name: "Principal" }).last();
  await expect(bottomNav).toBeVisible();
  await expect(bottomNav.getByRole("link", { name: "Inicio" })).toHaveAttribute("aria-current", "page");
  await page.getByRole("button", { name: "Crear" }).click();
  await expect(page.getByRole("dialog", { name: "Crear" })).toBeVisible();
  await page.getByRole("link", { name: "Nuevo presupuesto" }).click();
  await expect(page).toHaveURL(/\/budgets\/new$/);

  // "Más" abre todas las secciones que no entran en la barra (antes llevaba solo a Configuración).
  await bottomNav.getByRole("button", { name: "Más" }).click();
  const more = page.getByRole("dialog", { name: "Más secciones" });
  for (const name of ["Mis tareas", "Actividad", "Catálogo", "Clientes", "Proveedores", "Reportes", "Configuración"]) {
    await expect(more.getByRole("link", { name })).toBeVisible();
  }
  await more.getByRole("link", { name: "Clientes" }).click();
  await expect(page).toHaveURL(/\/clients$/);
});

test("en desktop hay sidebar y ⌘K navega", async ({ page, isMobile }) => {
  test.skip(isMobile, "solo desktop");
  await login(page);
  await page.keyboard.press("Control+k");
  await page.getByRole("textbox", { name: "Buscar sección" }).fill("audit");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/settings\/audit$/);
});
