"use client";

import { useQuery } from "@tanstack/react-query";

import { cn } from "@/lib/cn";
import { api, unwrap } from "@/lib/api/client";
import type { ChargeMode, Cost } from "@/lib/api/types";
import { formatDay } from "@/lib/format/date";
import { formatMoney, formatPercent } from "@/lib/format/number";

export const CATALOG_KEY = ["catalog"] as const;
export const SUPPLIERS_KEY = ["suppliers"] as const;
export const PRODUCTS_KEY = ["products"] as const;

export const CHARGE_MODE_LABELS: Record<ChargeMode, string> = {
  FIXED: "Precio fijo",
  PER_DAY: "Por día",
};

/** Alícuotas de IVA habituales. El valor es la fracción tal como la espera la API. */
export const IVA_OPTIONS = [
  { value: "0.21", label: "21 %" },
  { value: "0.105", label: "10,5 %" },
  { value: "0.27", label: "27 %" },
  { value: "0", label: "0 % (exento)" },
];

/** "0.2100" → "0.21": para comparar con las opciones del select. */
export function normalizeRate(rate: string): string {
  return rate.includes(".") ? rate.replace(/0+$/, "").replace(/\.$/, "") : rate;
}

/** "0.2100" → "21 %", "0.1050" → "10,5 %". */
export function ivaLabel(rate: string): string {
  return formatPercent(rate, 1).replace(",0 %", " %");
}

export function useCategories() {
  return useQuery({
    queryKey: [...CATALOG_KEY, "categories"],
    queryFn: async () => unwrap(await api.GET("/api/v1/categories")),
    staleTime: 60_000,
  });
}

export function useUnits() {
  return useQuery({
    queryKey: [...CATALOG_KEY, "units"],
    queryFn: async () => unwrap(await api.GET("/api/v1/units")),
    staleTime: 5 * 60_000,
  });
}

export function useSuppliers(q = "") {
  return useQuery({
    queryKey: [...SUPPLIERS_KEY, "list", q],
    queryFn: async () => unwrap(await api.GET("/api/v1/suppliers", { params: { query: { q: q || undefined } } })),
  });
}

export function StaleBadge({ cost }: { cost: Cost }) {
  return (
    <span
      className={cn(
        "rounded px-1.5 py-0.5 text-xs",
        cost.stale ? "bg-warning/15 text-warning" : "bg-subtle text-ink-muted",
      )}
      title={`Vigente desde ${formatDay(cost.valid_from)}`}
    >
      {cost.stale ? `Desactualizado · ${cost.days_old} días` : cost.days_old === 0 ? "Hoy" : `Hace ${cost.days_old} días`}
    </span>
  );
}

/** Un costo tal como lo cargó el proveedor: el monto, si incluye IVA y su antigüedad. */
export function CostLabel({ cost, compact = false }: { cost: Cost | null | undefined; compact?: boolean }) {
  if (!cost) return <span className="text-sm text-ink-muted">Sin costo</span>;
  return (
    <span className="inline-flex flex-wrap items-center gap-x-2 gap-y-1">
      <span className="font-medium tabular-nums">{formatMoney(cost.amount, cost.currency)}</span>
      <span className="text-xs text-ink-muted">
        {cost.includes_iva ? "IVA incl." : `+ IVA ${ivaLabel(cost.iva_rate)}`}
      </span>
      {compact && !cost.stale ? null : <StaleBadge cost={cost} />}
    </span>
  );
}
