import { describe, expect, it } from "vitest";

import { formatDay, todayInArgentina } from "./date";

describe("formatDay", () => {
  it("formatea sin correr el día por zona horaria", () => {
    expect(formatDay("2026-10-05")).toBe("05/10/2026");
    expect(formatDay("2026-01-01")).toBe("01/01/2026");
  });

  it("rechaza lo que no es una fecha", () => {
    expect(() => formatDay("05/10/2026")).toThrow();
  });
});

describe("todayInArgentina", () => {
  it("usa la hora de Buenos Aires (UTC-3)", () => {
    // 02:00 UTC del 6 de octubre son las 23:00 del 5 en Argentina.
    expect(todayInArgentina(new Date("2026-10-06T02:00:00Z"))).toBe("2026-10-05");
    expect(todayInArgentina(new Date("2026-10-06T03:00:00Z"))).toBe("2026-10-06");
  });
});
