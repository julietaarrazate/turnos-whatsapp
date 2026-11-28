import { expect, test } from "@playwright/test";

import { H, login } from "./helpers";

test("bloqueo con PIN: se activa en Mi perfil y destraba con el PIN correcto", async ({ page }) => {
  await login(page);
  await page.goto("/settings/account");
  await expect(page.getByRole("heading", { name: "Mi perfil" })).toBeVisible();
  await page.getByRole("button", { name: "Activar bloqueo con PIN" }).click();
  const dialog = page.getByRole("dialog", { name: "Configurar PIN" });
  await dialog.getByLabel("Nuevo PIN").fill("2580");
  await dialog.getByLabel("Repetí el PIN").fill("2580");
  await dialog.getByRole("button", { name: "Activar" }).click();
  await expect(page.getByText("Activado", { exact: true })).toBeVisible();

  // Como si hubiera quedado minimizada: al volver, pide el PIN.
  await page.evaluate(() => sessionStorage.setItem("handie-locked", "1"));
  await page.reload();
  const lock = page.getByRole("dialog", { name: "Handie está bloqueada" });
  await expect(lock).toBeVisible();
  for (const digit of "0000") await lock.getByRole("button", { name: digit, exact: true }).click();
  await expect(lock.getByText("PIN incorrecto. Te quedan 4 intentos.")).toBeVisible();
  for (const digit of "2580") await lock.getByRole("button", { name: digit, exact: true }).click();
  await expect(lock).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Mi perfil" })).toBeVisible();

  // Se deja como estaba para el resto de las pruebas (mismo usuario del seed).
  await page.request.delete("/api/v1/auth/pin", { headers: H });
});
