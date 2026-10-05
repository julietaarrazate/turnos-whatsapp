"use client";

import { useQuery } from "@tanstack/react-query";
import { Plus, Search } from "lucide-react";
import { useDeferredValue, useId, useState } from "react";

import { api, unwrap } from "@/lib/api/client";
import type { ProductSummary } from "@/lib/api/types";
import { formatMoney } from "@/lib/format/number";

/** Buscador del catálogo para agregar una línea. Teclado primero: ↑ ↓ Enter, Esc limpia. */
export function ProductSearch({
  onPick,
  onFree,
  disabled,
}: {
  onPick: (product: ProductSummary) => void;
  onFree: (name: string) => void;
  disabled?: boolean;
}) {
  const listId = useId();
  const [text, setText] = useState("");
  const [cursor, setCursor] = useState(0);
  const q = useDeferredValue(text.trim());
  const results = useQuery({
    queryKey: ["products", "search", q],
    queryFn: async () => unwrap(await api.GET("/api/v1/products", { params: { query: { q, limit: 8 } } })),
    enabled: q.length >= 2,
  });
  const items = q.length >= 2 ? (results.data?.items ?? []) : [];
  const options = [...items.map((p) => ({ kind: "product" as const, product: p })), ...(q ? [{ kind: "free" as const }] : [])];

  function choose(index: number) {
    const option = options[index];
    if (!option) return;
    if (option.kind === "product") onPick(option.product);
    else onFree(text.trim());
    setText("");
    setCursor(0);
  }

  return (
    <div className="relative">
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-muted" aria-hidden />
        <input
          role="combobox"
          aria-expanded={options.length > 0}
          aria-controls={listId}
          aria-label="Agregar ítem"
          placeholder="Agregar ítem: buscá en el catálogo o escribí uno nuevo"
          value={text}
          disabled={disabled}
          onChange={(e) => {
            setText(e.target.value);
            setCursor(0);
          }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setCursor((c) => Math.min(c + 1, options.length - 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setCursor((c) => Math.max(c - 1, 0));
            } else if (e.key === "Enter") {
              e.preventDefault();
              choose(cursor);
            } else if (e.key === "Escape") {
              setText("");
            }
          }}
          className="h-11 w-full rounded-lg border border-dashed border-line bg-surface pl-9 pr-3 text-base placeholder:text-ink-muted focus:border-accent focus:outline-2 focus:outline-accent/30 sm:h-10 sm:text-sm"
        />
      </div>
      {options.length > 0 ? (
        <ul
          id={listId}
          role="listbox"
          className="absolute z-20 mt-1 max-h-80 w-full overflow-y-auto rounded-lg border border-line bg-surface py-1 shadow-lg"
        >
          {options.map((option, index) => (
            <li
              key={option.kind === "product" ? option.product.id : "free"}
              role="option"
              aria-selected={index === cursor}
              onMouseDown={(e) => {
                e.preventDefault();
                choose(index);
              }}
              onMouseEnter={() => setCursor(index)}
              className={`flex cursor-pointer items-center gap-3 px-3 py-2 text-sm ${index === cursor ? "bg-subtle" : ""}`}
            >
              {option.kind === "product" ? (
                <>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">{option.product.name}</span>
                    <span className="block truncate text-xs text-ink-muted">
                      {option.product.category_name} · por {option.product.unit_code}
                      {option.product.preferred ? ` · ${option.product.preferred.supplier_name}` : " · sin proveedor"}
                    </span>
                  </span>
                  {option.product.preferred?.current_cost ? (
                    <span className="text-xs tabular-nums text-ink-muted">
                      {formatMoney(option.product.preferred.current_cost.amount)}
                    </span>
                  ) : null}
                </>
              ) : (
                <span className="flex items-center gap-2 text-ink-muted">
                  <Plus className="size-4" aria-hidden /> Ítem libre: “{text.trim()}”
                </span>
              )}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
