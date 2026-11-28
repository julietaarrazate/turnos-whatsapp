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
  await page.getByLabel("Contraseña", { exact: true }).fill("no-es-la-clave");
  await page.getByRole("button", { name: "Ingresar" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "incorrectos" })).toHaveText(
    "Email o contraseña incorrectos",
  );
});

test("se puede ver la contraseña mientras se escribe", async ({ page }) => {
  await page.goto("/login");
  const password = page.getByLabel("Contraseña", { exact: true });
  const toggle = page.getByRole("button", { name: "Mostrar contraseña" });
  await password.fill("mi-clave");
  await expect(password).toHaveAttribute("type", "password");
  await toggle.click();
  await expect(password).toHaveAttribute("type", "text");
  await expect(toggle).toHaveAttribute("aria-pressed", "true");
  await expect(password).toHaveValue("mi-clave");
  await toggle.click();
  await expect(password).toHaveAttribute("type", "password");
});

test("cerrar sesión", async ({ page }) => {
  await login(page);
  await expect(page.getByRole("heading", { name: /Buen[oa]s/ })).toBeVisible();
  // Primero pregunta: si la persona dice que no, sigue adentro.
  const menu = page.getByRole("button", { name: "Abrir menú" });
  if (await menu.isVisible()) await menu.click();
  page.once("dialog", (dialog) => void dialog.dismiss());
  await page.getByRole("button", { name: "Cerrar sesión" }).first().click();
  await expect(page.getByRole("heading", { name: /Buen[oa]s/ })).toBeVisible();
  page.once("dialog", (dialog) => void dialog.accept());
  await page.getByRole("button", { name: "Cerrar sesión" }).first().click();
  await expect(page).toHaveURL(/\/login/);
  await page.goto("/");
  await expect(page).toHaveURL(/\/login/);
});
