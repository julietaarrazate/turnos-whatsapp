import { describe, expect, it } from "vitest";

import { groupFiles } from "./event-files";

const item = (over: Record<string, unknown>) =>
  ({
    id: "x",
    source: "FILE",
    category: "CLIENT",
    title: "t",
    piece_id: null,
    piece_name: null,
    href: "/",
    mime: null,
    version: null,
    current: null,
    expires_soon: false,
    author_name: "Vale",
    created_at: "2026-11-26T12:00:00Z",
    event: { id: "e", number: 1, name: "Natura" },
    can_delete: true,
    ...over,
  }) as Parameters<typeof groupFiles>[0][number];

describe("archivos del evento", () => {
  it("ordena por secciones fijas y saca las vacías", () => {
    const groups = groupFiles([
      item({ id: "a", category: "PROGRESS", source: "PHOTO" }),
      item({ id: "b", category: "CLIENT" }),
      item({ id: "c", category: "DESIGN" }),
    ]);
    expect(groups.map((g) => g.label)).toEqual(["Del cliente", "Diseño", "Avances"]);
  });

  it("en Diseño, las versiones viejas de un plano van al final", () => {
    const [design] = groupFiles([
      item({ id: "v1", category: "DESIGN", source: "PLAN", version: 1, current: false }),
      item({ id: "render", category: "DESIGN", source: "LINK" }),
      item({ id: "v2", category: "DESIGN", source: "PLAN", version: 2, current: true }),
    ]);
    expect(design.items.map((i) => i.id)).toEqual(["render", "v2", "v1"]);
  });
});
