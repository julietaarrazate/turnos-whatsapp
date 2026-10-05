import { expect, test } from "@playwright/test";

import { OWNER, login } from "./helpers";

test("una ruta protegida manda al login y vuelve a donde estaba", async ({ page }) => {
  await login(page, "/settings/members");
  await expect(page).toHaveURL(/\/settings\/members$/);
  await expect(page.getByRole("heading", { name: "Usuarios y roles" })).toBeVisible();
});

test("contraseña incorrecta muestra un error claro", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(OWNER.email);
  await page.getByLabel("Contraseña").fill("no-es-la-clave");
  await page.getByRole("button", { name: "Ingresar" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "incorrectos" })).toHaveText(
    "Email o contraseña incorrectos",
  );
});

test("cerrar sesión", async ({ page }) => {
  await login(page);
  await expect(page.getByRole("heading", { name: /Buen[oa]s/ })).toBeVisible();
  await page.getByRole("button", { name: "Cerrar sesión" }).first().click();
  await expect(page).toHaveURL(/\/login/);
  await page.goto("/");
  await expect(page).toHaveURL(/\/login/);
});
