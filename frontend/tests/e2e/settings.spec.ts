import { expect, test } from "@playwright/test";

import { login } from "./helpers";

test("invitar y anular una invitación", async ({ page, browser }) => {
  const email = `e2e-${Date.now()}@example.com`;
  await login(page, "/settings/members");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Rol", { exact: true }).selectOption("PRODUCTION");
  await page.getByRole("button", { name: "Invitar" }).click();
  // Sin email configurado, el link se muestra para mandarlo a mano (copiar o WhatsApp).
  await expect(page.getByText(`Invitación creada para ${email}. Mandale este link:`)).toBeVisible();
  const link = await page.getByLabel("Link de la invitación").inputValue();
  expect(link).toMatch(/\/invite\/\S+$/);
  await expect(page.getByRole("link", { name: "WhatsApp" })).toHaveAttribute("href", /^https:\/\/wa\.me\/\?text=.+%2Finvite%2F/);
  // El link funciona para quien lo recibe (sin sesión).
  const guest = await browser.newPage();
  await guest.goto(link);
  await expect(guest.getByText(`Invitación para ${email} como Producción.`)).toBeVisible();
  // La contraseña nueva se puede mostrar para revisarla antes de aceptar.
  const password = guest.getByLabel("Elegí una contraseña", { exact: true });
  await password.fill("clave-larga-123");
  await guest.getByRole("button", { name: "Mostrar contraseña" }).click();
  await expect(password).toHaveAttribute("type", "text");
  await guest.close();

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
  await expect(page.getByText(`Nombre: ${name}`)).toBeVisible();
});
