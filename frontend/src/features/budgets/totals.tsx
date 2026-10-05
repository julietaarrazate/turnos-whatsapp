"use client";

import { AlertTriangle } from "lucide-react";

import { pct } from "@/features/pricing/shared";
import type { BudgetVersion } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatMoney } from "@/lib/format/number";

const WARNINGS: Record<string, string> = {
  below_cost: "Hay ítems (o el total) por debajo del costo.",
  below_min_margin: "El margen quedó por debajo del mínimo de la organización.",
  target_rounded: "El precio objetivo se redondeó al incremento comercial.",
};

function Figure({ label, value, strong, tone }: { label: string; value: string; strong?: boolean; tone?: string }) {
  return (
    <div className="min-w-0">
      <p className="truncate text-[11px] uppercase tracking-wide text-ink-muted">{label}</p>
      <p className={cn("truncate tabular-nums", strong ? "text-base font-semibold" : "text-sm", tone)}>{value}</p>
    </div>
  );
}

/** Pie fijo con costo, venta, ganancia y margen: lo único que el cliente de esta pantalla mira siempre. */
export function TotalsFooter({ version, pending }: { version: BudgetVersion; pending: boolean }) {
  const margins = version.margins;
  const profitTone = margins && margins.profit.startsWith("-") ? "text-danger" : undefined;
  return (
    <section
      aria-label="Totales"
      className="sticky bottom-[calc(4rem+env(safe-area-inset-bottom))] z-10 -mx-4 mt-6 border-t border-line bg-surface/95 px-4 py-3 backdrop-blur lg:bottom-0 lg:mx-0 lg:rounded-t-xl lg:border-x"
    >
      <div className={cn("grid grid-cols-3 gap-3 sm:grid-cols-6", pending && "opacity-60 transition-opacity")} aria-busy={pending}>
        {version.costs ? <Figure label="Costo" value={formatMoney(version.costs.cost_direct)} /> : null}
        <Figure label="Venta neta" value={formatMoney(version.sale_net)} strong />
        {margins ? <Figure label="Ganancia" value={formatMoney(margins.profit)} tone={profitTone} /> : null}
        {margins ? (
          <Figure
            label={margins.sale_charges !== "0.00" ? "Margen (desp. cargos)" : "Margen"}
            value={margins.margin_net ? pct(margins.margin_net) : "—"}
            tone={profitTone}
          />
        ) : null}
        <Figure label="IVA" value={formatMoney(version.iva)} />
        <Figure label="Total" value={formatMoney(version.total)} strong />
      </div>
      {version.presentation ? (
        <p className="mt-1 text-xs text-ink-muted">
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
