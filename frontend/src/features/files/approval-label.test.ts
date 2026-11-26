import { describe, expect, it } from "vitest";

import { approvalLabel } from "./event-files";

const base = {
  id: "a",
  requested_at: "2026-11-26T12:00:00Z",
  decided_at: null,
  decided_by_name: null,
  comment: null,
  rounds: 1,
};

describe("estado de la aprobación del cliente", () => {
  it("dice quién aprobó, o qué cambios pidió, o que se espera respuesta", () => {
    expect(approvalLabel({ ...base, status: "PENDING" }).text).toBe("Esperando respuesta del cliente");
    expect(approvalLabel({ ...base, status: "APPROVED", decided_by_name: "Laura" }).text).toBe("✓ Aprobado por Laura");
    expect(approvalLabel({ ...base, status: "CHANGES", comment: "Logo más grande", rounds: 2 }).text).toBe(
      "Pidió cambios (vuelta 2): “Logo más grande”",
    );
  });
});
