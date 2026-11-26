import { describe, expect, it, vi } from "vitest";

import { confirmLogout } from "./app-shell";

describe("cerrar sesión", () => {
  it("pregunta antes y solo sale si la persona confirma", () => {
    const logout = vi.fn(() => Promise.resolve());
    confirmLogout(logout, () => false);
    expect(logout).not.toHaveBeenCalled();
    confirmLogout(logout, () => true);
    expect(logout).toHaveBeenCalledOnce();
  });
});
