"use client";

import { AlertTriangle, ChevronUp } from "lucide-react";
import { useState } from "react";

import { pct } from "@/features/pricing/shared";
import type { BudgetVersion } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatMoney } from "@/lib/format/number";

const WARNINGS: Record<string, string> = {
  below_cost: "Hay ítems (o el total) por debajo del costo.",
  below_min_margin: "El margen quedó por debajo del mínimo de la organización.",
  target_rounded: "El precio objetivo no dio exacto: se redondeó al incremento comercial (o al centavo del fee).",
};

function Figure({
  label,
  value,
  strong,
  tone,
  className,
}: {
  label: string;
  value: string;
  strong?: boolean;
  tone?: string;
  className?: string;
}) {
  return (
    <div className={cn("min-w-0", className)}>
      <p className="truncate text-[11px] uppercase tracking-wide text-ink-muted">{label}</p>
      <p className={cn("truncate tabular-nums", strong ? "text-base font-semibold" : "text-sm", tone)}>{value}</p>
    </div>
  );
}

/** Pie fijo con costo, venta, ganancia y margen: lo único que el cliente de esta pantalla mira siempre.
 * En el celular es una sola línea (total y margen) que se despliega con un toque. */
export function TotalsFooter({ version, pending }: { version: BudgetVersion; pending: boolean }) {
  const [open, setOpen] = useState(false);
  const margins = version.margins;
  const profitTone = margins && margins.profit.startsWith("-") ? "text-danger" : undefined;
  return (
    <section
      aria-label="Totales"
      className="sticky bottom-[calc(4.5rem+env(safe-area-inset-bottom))] z-10 -mx-4 mt-6 border-t border-line bg-surface/95 px-4 py-2 shadow-[0_-4px_12px_rgba(0,0,0,0.06)] backdrop-blur lg:bottom-0 lg:mx-0 lg:rounded-t-xl lg:border-x lg:py-3"
    >
      <button
        type="button"
        aria-expanded={open}
        aria-label={open ? "Ocultar el detalle de los totales" : "Ver el detalle de los totales"}
        onClick={() => setOpen((v) => !v)}
        className={cn("flex w-full items-center gap-3 py-1 text-left lg:hidden", pending && "opacity-60")}
      >
        <span className="min-w-0 flex-1">
          <span className="block text-[11px] tracking-wide text-ink-muted uppercase">Total con IVA</span>
          <span className="block truncate text-lg font-bold text-ink tabular-nums">{formatMoney(version.total)}</span>
        </span>
        {margins ? (
          <span className="text-right">
            <span className="block text-[11px] tracking-wide text-ink-muted uppercase">Margen</span>
            <span className={cn("block font-bold tabular-nums", profitTone ?? "text-success")}>
              {margins.margin_net ? pct(margins.margin_net) : "—"}
            </span>
          </span>
        ) : null}
        <ChevronUp className={cn("size-5 shrink-0 text-ink-muted transition-transform", open && "rotate-180")} aria-hidden />
      </button>
      <div
        className={cn("grid-cols-2 gap-3 pt-2 sm:grid-cols-4 lg:grid-cols-6 lg:grid lg:pt-0", open ? "grid" : "hidden", pending && "opacity-60 transition-opacity")}
        aria-busy={pending}
      >
        {version.costs ? <Figure label="Costo" value={formatMoney(version.costs.cost_direct)} /> : null}
        <Figure label="Venta neta" value={formatMoney(version.sale_net)} strong />
        {margins ? <Figure label="Ganancia" value={formatMoney(margins.profit)} tone={profitTone} /> : null}
        {margins ? (
          <Figure
            label={margins.sale_charges !== "0.00" ? "Margen (desp. cargos)" : "Margen"}
            value={margins.margin_net ? pct(margins.margin_net) : "—"}
            tone={profitTone}
            className="hidden lg:block"
          />
        ) : null}
        <Figure label="IVA" value={formatMoney(version.iva)} />
        <Figure label="Total" value={formatMoney(version.total)} strong className="hidden lg:block" />
      </div>
      {version.management_fee !== "0.00" ? (
        <p className={cn("mt-1 text-xs text-ink-muted lg:block", open ? "block" : "hidden")}>
          La venta neta incluye el fee de gestión ({pct(version.management_fee_rate)}): {formatMoney(version.management_fee)}
        </p>
      ) : null}
      {version.presentation ? (
        <p className={cn("mt-1 text-xs text-ink-muted lg:block", open ? "block" : "hidden")}>
          En dólares (US$ 1 = {formatMoney(version.presentation.fx_rate)}): neto{" "}
          {formatMoney(version.presentation.net, "USD")} · total {formatMoney(version.presentation.total, "USD")}
        </p>
      ) : null}
      {version.warnings.length ? (
        <ul className="mt-2 flex flex-col gap-1">
          {version.warnings.map((w) => (
            <li key={w} className="flex items-center gap-2 text-xs text-warning">
              <AlertTriangle className="size-3.5" aria-hidden /> {WARNINGS[w] ?? w}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
