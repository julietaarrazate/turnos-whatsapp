import { expect, test } from "@playwright/test";

import { H, json, login } from "./helpers";

test("la ficha del lugar se arma una vez y el próximo evento en el mismo lugar ya la tiene", async ({ page }, testInfo) => {
  const suffix = `${testInfo.project.name}-lugar-${Date.now()}`;
  const venue = `Predio ${suffix}`;
  await login(page);
  const newEvent = async (name: string) =>
    (await json<{ id: string }>(
      await page.request.post("/api/v1/events", { headers: H, data: { client_name: `Cliente ${suffix}`, name, venue } }),
    )).id;

  const first = await newEvent(`Expo ${suffix}`);
  await page.goto(`/events/${first}`);
  const card = page.getByRole("region", { name: `Ficha del lugar: ${venue}` });
  await card.getByRole("button", { name: "Armar ficha" }).click();
  await card.getByRole("textbox", { name: "Carga y accesos" }).fill("Por calle Sarmiento, de 7 a 10");
  await card.getByRole("textbox", { name: "Contactos" }).fill("Seguridad: Juan 11 5555-0000");
  await card.getByRole("button", { name: "Guardar ficha" }).click();
  await expect(card.getByText("Por calle Sarmiento, de 7 a 10")).toBeVisible();

  const second = await newEvent(`Lanzamiento ${suffix}`);
  await page.goto(`/events/${second}`);
  const reused = page.getByRole("region", { name: `Ficha del lugar: ${venue}` });
  await expect(reused.getByText("Seguridad: Juan 11 5555-0000")).toBeVisible();
  await expect(reused.getByText(/Ya trabajaron ahí en 1 evento/)).toBeVisible();
});
