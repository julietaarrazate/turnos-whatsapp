import { expect, test, type Page } from "@playwright/test";

import { login } from "./helpers";

/** Junta las violaciones de CSP que reporta el navegador (una CSP mal armada rompe la app en silencio). */
async function watchViolations(page: Page) {
  await page.addInitScript(() => {
    const w = window as unknown as { __cspViolations: string[] };
    w.__cspViolations = [];
    document.addEventListener("securitypolicyviolation", (e) =>
      w.__cspViolations.push(`${e.violatedDirective} ${e.blockedURI || "inline"}`),
    );
  });
  return () => page.evaluate(() => (window as unknown as { __cspViolations: string[] }).__cspViolations);
}

test("las páginas mandan una CSP con nonce y ninguna pantalla la viola", async ({ page }) => {
  const violations = await watchViolations(page);
  const response = await page.goto("/login");
  const csp = response?.headers()["content-security-policy"] ?? "";
  expect(csp).toMatch(/script-src 'self' 'nonce-[^']+' 'strict-dynamic'/);
  expect(csp).not.toContain("unsafe-inline");
  await expect(page.getByRole("button", { name: "Ingresar" })).toBeVisible();

  await login(page);
  for (const path of ["/budgets", "/events", "/catalog", "/clients", "/suppliers", "/reports", "/settings/members"]) {
    await page.goto(path);
    await expect(page.getByRole("button", { name: "Cerrar sesión" }).first()).toBeVisible();
  }
  // Navegación del lado del cliente (sin recargar).
  await page.getByRole("link", { name: "Presupuestos", exact: true }).filter({ visible: true }).first().click();
  await expect(page).toHaveURL(/\/budgets$/);
  expect(await violations()).toEqual([]);
});

test("la CSP bloquea scripts que no vienen de la app", async ({ page }) => {
  const violations = await watchViolations(page);
  // Simula una inyección: el HTML llega con scripts que no tienen el nonce del request.
  await page.route("**/login", async (route) => {
    const response = await route.fetch();
    const html = (await response.text()).replace(
      "</body>",
      '<script>window.__pwned=true</script><img src="x" onerror="window.__pwned=true"></body>',
    );
    await route.fulfill({ response, body: html });
  });
  await page.goto("/login");
  await expect(page.getByRole("button", { name: "Ingresar" })).toBeVisible();
  expect(await page.evaluate(() => "__pwned" in window)).toBe(false);
  expect(await violations()).toEqual(expect.arrayContaining(["script-src-elem inline", "script-src-attr inline"]));
});
