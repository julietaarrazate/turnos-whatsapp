import { describe, expect, it } from "vitest";

import { renewSession } from "./client";

const res = (status: number) => Promise.resolve(new Response(null, { status }));
const noWait = () => Promise.resolve();

describe("renovar la sesión", () => {
  it("con 200 sigue, con 401 pide ingresar de nuevo", async () => {
    expect(await renewSession(() => res(200), [1], noWait)).toBe("ok");
    expect(await renewSession(() => res(401), [1], noWait)).toBe("expired");
  });

  it("si el servidor está despertando (502, sin red), reintenta en vez de sacar a la persona", async () => {
    const answers = [() => res(502), () => Promise.reject(new TypeError("sin red")), () => res(200)];
    let calls = 0;
    const result = await renewSession(() => answers[calls++](), [1, 1, 1], noWait);
    expect(result).toBe("ok");
    expect(calls).toBe(3);
  });

  it("si nunca despierta, avisa que no está disponible (no manda al ingreso)", async () => {
    let calls = 0;
    const result = await renewSession(() => (calls++, res(503)), [1, 1], noWait);
    expect(result).toBe("unavailable");
    expect(calls).toBe(3);
  });
});
