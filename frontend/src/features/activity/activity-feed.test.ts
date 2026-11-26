import { describe as group, expect, it } from "vitest";

import { describe, timeAgo } from "./activity-feed";

const base = {
  id: "1",
  actor_name: "Vale",
  event: { id: "e", number: 3, name: "Natura" },
  piece: "Mostrador",
  status: null,
  supplier: null,
  title: null,
  version: null,
  note: null,
  update_id: null,
  has_photo: false,
  has_audio: false,
  created_at: "2026-11-26T12:00:00Z",
};

group("actividad", () => {
  it("arma cada frase en castellano", () => {
    expect(describe({ ...base, kind: "piece.status_changed", status: "IN_WORKSHOP" })).toBe("pasó Mostrador a En taller");
    expect(describe({ ...base, kind: "piece.update_posted", has_photo: true })).toBe("subió una foto de avance de Mostrador");
    expect(describe({ ...base, kind: "piece.update_posted" })).toBe("dejó una nota en Mostrador");
    expect(describe({ ...base, kind: "piece.update_posted", has_audio: true })).toBe("dejó una nota de voz en Mostrador");
    expect(describe({ ...base, kind: "piece.plan_uploaded", title: "Plano de corte", version: 2 })).toBe(
      "subió Plano de corte v2 de Mostrador",
    );
    expect(describe({ ...base, kind: "production.supplier_status", supplier: "Sonido Sur", status: "CONFIRMED" })).toBe(
      "marcó Sonido Sur como confirmado",
    );
    expect(describe({ ...base, kind: "algo.nuevo" })).toBe("hizo un cambio");
  });

  it("dice hace cuánto pasó", () => {
    const now = new Date("2026-11-26T12:00:00Z");
    expect(timeAgo("2026-11-26T11:59:50Z", now)).toBe("recién");
    expect(timeAgo("2026-11-26T11:55:00Z", now)).toBe("hace 5 min");
    expect(timeAgo("2026-11-26T09:00:00Z", now)).toBe("hace 3 h");
    expect(timeAgo("2026-11-25T10:00:00Z", now)).toBe("ayer");
  });
});
