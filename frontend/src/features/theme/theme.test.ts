import { describe, expect, it } from "vitest";

import { applyTheme, readTheme } from "./theme";

describe("modo oscuro", () => {
  it("lee la elección guardada y, si no hay o falla, sigue al teléfono", () => {
    expect(readTheme({ getItem: () => "dark" })).toBe("dark");
    expect(readTheme({ getItem: () => "cualquiera" })).toBe("system");
    expect(readTheme({ getItem: () => { throw new Error("bloqueado"); } })).toBe("system");
    expect(readTheme(undefined)).toBe("system");
  });

  it("Claro u Oscuro lo fija en <html>; Automático lo saca", () => {
    const root = { dataset: {} as Record<string, string> } as unknown as HTMLElement;
    applyTheme("dark", root);
    expect(root.dataset.theme).toBe("dark");
    applyTheme("system", root);
    expect(root.dataset.theme).toBeUndefined();
  });
});
