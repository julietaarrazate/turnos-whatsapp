import { expect, type Page } from "@playwright/test";

/** Usuario de `make seed` (backend/scripts/seed_dev.py). */
export const OWNER = { email: "owner@demo.example.com", password: "demo-demo-1234" };

export async function login(page: Page, next = "/") {
  await page.goto(next);
  await expect(page).toHaveURL(/\/login/);
  await page.getByLabel("Email").fill(OWNER.email);
  await page.getByLabel("Contraseña", { exact: true }).fill(OWNER.password);
  await page.getByRole("button", { name: "Ingresar" }).click();
  // Esperar a que la app autenticada esté montada (no solo a que cambie la URL).
  await expect(page).not.toHaveURL(/\/login/);
  await expect(page.getByRole("button", { name: "Cerrar sesión" }).first()).toBeVisible();
}
