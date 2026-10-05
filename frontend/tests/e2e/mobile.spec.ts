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
  await expect(page.getByRole("button", { name: /Nuevo presupuesto/ })).toBeDisabled();
});

test("en desktop hay sidebar y ⌘K navega", async ({ page, isMobile }) => {
  test.skip(isMobile, "solo desktop");
  await login(page);
  await page.keyboard.press("Control+k");
  await page.getByRole("textbox", { name: "Buscar sección" }).fill("audit");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/settings\/audit$/);
});
