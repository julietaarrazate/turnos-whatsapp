import { expect, test } from "@playwright/test";

import { H, OWNER, json } from "./helpers";

test("crear cuenta: queda esperando aprobación y entra cuando la dueña la aprueba", async ({ page, playwright, baseURL }) => {
  const email = `nueva-${Date.now()}-${Math.round(Math.random() * 1e6)}@example.com`;
  const organization = `Productora ${email.slice(6, 19)}`;

  await page.goto("/login");
  await page.getByRole("link", { name: "Creá una" }).click();
  await expect(page).toHaveURL(/\/signup$/);
  await page.getByLabel("Nombre y apellido").fill("Ana Pérez");
  await page.getByLabel("Nombre de tu productora").fill(organization);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Elegí una contraseña", { exact: true }).fill(OWNER.password);
  await page.getByRole("button", { name: "Crear cuenta" }).click();

  await expect(page.getByRole("heading", { name: "Tu cuenta está esperando aprobación" })).toBeVisible();
  await expect(page.getByText(organization)).toBeVisible();

  // La dueña de la plataforma la aprueba desde el panel (acá, por API).
  const admin = await playwright.request.newContext({ baseURL, extraHTTPHeaders: H });
  await json(await admin.post("/api/v1/auth/login", { data: { email: "admin@demo.example.com", password: OWNER.password } }));
  const overview = await json<{ organizations: { id: string; name: string; pending_approval: boolean }[] }>(
    await admin.get("/api/v1/admin/overview"),
  );
  const org = overview.organizations.find((o) => o.name === organization);
  expect(org?.pending_approval).toBe(true);
  expect((await admin.post(`/api/v1/admin/organizations/${org!.id}/approve`)).status()).toBe(204);
  await admin.dispose();

  await page.getByRole("button", { name: "Ya me avisaron, volver a revisar" }).click();
  await expect(page.getByRole("button", { name: /^(Cerrar sesión|Abrir menú)$/ }).first()).toBeVisible();
});
