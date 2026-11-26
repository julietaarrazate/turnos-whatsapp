import { describe, expect, it } from "vitest";

import { keyBytes } from "./push";

describe("clave para los avisos", () => {
  it("pasa de base64url a bytes como la pide el navegador", () => {
    expect(Array.from(keyBytes("AQID_-8"))).toEqual([1, 2, 3, 255, 239]);
    expect(keyBytes("A".repeat(87)).length).toBe(65); // punto P-256 sin comprimir
  });
});
