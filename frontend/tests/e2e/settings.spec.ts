import { expect, test } from "@playwright/test";

import { login } from "./helpers";

test("invitar y anular una invitación", async ({ page }) => {
  const email = `e2e-${Date.now()}@example.com`;
  await login(page, "/settings/members");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Rol", { exact: true }).selectOption("PRODUCTION");
  await page.getByRole("button", { name: "Invitar" }).click();
  await expect(page.getByRole("status").filter({ hasText: email })).toContainText("Invitación enviada");

  const row = page.getByRole("listitem").filter({ hasText: email });
  await expect(row).toContainText("Producción");
  await row.getByRole("button", { name: "Anular" }).click();
  await expect(row).toHaveCount(0);
});

test("la auditoría registra los cambios", async ({ page }) => {
  await login(page, "/settings/organization");
  const name = `Productora Demo ${Date.now() % 1000}`;
  await page.getByLabel("Nombre").fill(name);
  await page.getByRole("button", { name: "Guardar", exact: true }).click();
  await page.goto("/settings/audit");
  await expect(page.getByText(`name: ${name}`)).toBeVisible();
});
