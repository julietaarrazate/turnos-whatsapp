import { expect, test } from "@playwright/test";

import { OWNER, login } from "./helpers";

/** Usuario del seed configurado en PLATFORM_ADMINS (e2e.yml). */
const PLATFORM_ADMIN = { email: "admin@demo.example.com", password: OWNER.password };

test("la dueña de la plataforma ve el panel con organizaciones, personas y sesiones", async ({ page }) => {
  await login(page, "/", PLATFORM_ADMIN);
  const menu = page.getByRole("button", { name: "Abrir menú" });
  if (await menu.isVisible()) await menu.click();
  await page.getByRole("link", { name: "Administración" }).first().click();

  await expect(page).toHaveURL(/\/admin$/);
  await expect(page.getByRole("heading", { name: "Administración" })).toBeVisible();
  await expect(page.getByText("Organizaciones", { exact: true }).first()).toBeVisible();

  await page.getByRole("tab", { name: "Personas" }).click();
  await expect(page.getByText(OWNER.email)).toBeVisible();
  await expect(page.getByText("Vos", { exact: true })).toBeVisible();

  await page.getByRole("tab", { name: "Sesiones abiertas" }).click();
  await expect(page.getByText("(esta sesión)")).toBeVisible();

  await page.getByRole("tab", { name: "Organizaciones" }).click();
  await expect(page.getByRole("button", { name: "Pausar" }).first()).toBeVisible();
});

test("para cualquier otra persona el panel no existe", async ({ page }) => {
  await login(page, "/", OWNER);
  const menu = page.getByRole("button", { name: "Abrir menú" });
  if (await menu.isVisible()) await menu.click();
  await expect(page.getByRole("link", { name: "Administración" })).toHaveCount(0);

  await page.goto("/admin");
  await expect(page.getByText("Esta página no existe.")).toBeVisible();
  const api = await page.request.get("/api/v1/admin/overview", { headers: { "X-Requested-With": "fetch" } });
  expect(api.status()).toBe(404);
});
