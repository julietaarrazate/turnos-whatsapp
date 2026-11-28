import { describe, expect, it } from "vitest";

import { HIDDEN_LOCK_MS, IDLE_LOCK_MS, shouldLock } from "./lock";

describe("cuándo se bloquea la pantalla", () => {
  const now = 10_000_000;
  it("minimizada más de un minuto se bloquea; sacar una foto rápida no", () => {
    expect(shouldLock({ now, last: now, hiddenSince: now - HIDDEN_LOCK_MS - 1 })).toBe(true);
    expect(shouldLock({ now, last: now, hiddenSince: now - 20_000 })).toBe(false);
  });
  it("5 minutos sin tocar nada se bloquea", () => {
    expect(shouldLock({ now, last: now - IDLE_LOCK_MS - 1, hiddenSince: null })).toBe(true);
    expect(shouldLock({ now, last: now - 60_000, hiddenSince: null })).toBe(false);
    expect(shouldLock({ now, last: 0, hiddenSince: null })).toBe(false); // primera vez
  });
});
