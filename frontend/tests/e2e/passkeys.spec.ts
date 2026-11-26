import { expect, test } from "@playwright/test";

import { login } from "./helpers";

/** Huella simulada: Chromium trae un "autenticador virtual" que hace de lector de huellas. */
test("activar la huella y después entrar sin email ni contraseña", async ({ page, context }) => {
  const cdp = await context.newCDPSession(page);
  await cdp.send("WebAuthn.enable");
  await cdp.send("WebAuthn.addVirtualAuthenticator", {
    options: {
      protocol: "ctap2",
      transport: "internal",
      hasResidentKey: true,
      hasUserVerification: true,
      isUserVerified: true,
      automaticPresenceSimulation: true,
    },
  });

  await login(page);
  const offer = page.getByRole("region", { name: "Entrar más rápido" });
  await expect(offer).toBeVisible();
  await offer.getByRole("button", { name: "Activar" }).click();
  await expect(page.getByText("Listo: la próxima vez entrás con tu huella o cara.")).toBeVisible();

  page.once("dialog", (dialog) => void dialog.accept());
  await page.getByRole("button", { name: "Cerrar sesión" }).first().click();
  await expect(page).toHaveURL(/\/login/);

  await page.getByRole("button", { name: "Entrar con huella o cara" }).click();
  await expect(page).not.toHaveURL(/\/login/);
  await expect(page.getByRole("button", { name: "Cerrar sesión" }).first()).toBeVisible();
  // Ya activada: el aviso no vuelve a aparecer.
  await expect(page.getByRole("region", { name: "Entrar más rápido" })).toHaveCount(0);

  // En "Mi cuenta" se ve el dispositivo y se puede quitar.
  await page.goto("/settings/account");
  const remove = page.getByRole("button", { name: /^Quitar / });
  await expect(remove.first()).toBeVisible();
  const before = await remove.count();
  page.once("dialog", (dialog) => void dialog.accept());
  await remove.last().click();
  await expect(remove).toHaveCount(before - 1);
});
