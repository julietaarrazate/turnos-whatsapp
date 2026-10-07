"use client";

import { useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { useState } from "react";

import { SelectField, TextField } from "@/components/ui/field";
import { Notice } from "@/components/ui/notice";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import type { Schemas } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatMoney, formatPercentCompact } from "@/lib/format/number";

type Group = "event" | "client" | "month";
type Row = Schemas["ReportRow"];

function arDate(offsetMonths = 0): string {
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "America/Argentina/Buenos_Aires" }).format(new Date());
  if (!offsetMonths) return today;
  const [y, m] = today.split("-").map(Number);
  const first = new Date(Date.UTC(y, m - 1 + offsetMonths, 1));
  return first.toISOString().slice(0, 10);
}

function pct(value: string | null): string {
  return value === null ? "—" : value.startsWith("-") ? `−${formatPercentCompact(value.slice(1))}` : formatPercentCompact(value);
}

function ReportLine({ row, total }: { row: Row; total?: boolean }) {
  return (
    <tr className={cn(total && "bg-subtle font-semibold")}>
      <th scope="row" className="max-w-64 truncate px-3 py-2 text-left font-normal">
        {row.label}
        {row.partial && !total ? <span className="ml-1 text-xs text-ink-muted">(parcial)</span> : null}
      </th>
      <td className="px-3 py-2 text-right">{row.events}</td>
      <td className="px-3 py-2 text-right">{formatMoney(row.sale_net)}</td>
      <td className="px-3 py-2 text-right">{formatMoney(row.estimated_profit)}</td>
      <td className="px-3 py-2 text-right">{pct(row.estimated_margin)}</td>
      <td className="px-3 py-2 text-right">{row.actual_cost !== null ? formatMoney(row.actual_cost) : "—"}</td>
      <td className="px-3 py-2 text-right">{row.actual_profit !== null ? formatMoney(row.actual_profit) : "—"}</td>
      <td className="px-3 py-2 text-right">{pct(row.actual_margin)}</td>
      <td className="px-3 py-2 text-right">{row.cost_delta_rate !== null ? pct(row.cost_delta_rate) : "—"}</td>
    </tr>
  );
}

/** A-02: rentabilidad por evento, cliente o mes, con export CSV. */
export function ProfitabilityReport() {
  const [from, setFrom] = useState(() => arDate(-2));
  const [to, setTo] = useState(() => arDate());
  const [group, setGroup] = useState<Group>("event");
  const query = useQuery({
    queryKey: ["reports", "profitability", from, to, group],
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/reports/profitability", { params: { query: { from, to, group } } })),
    enabled: Boolean(from && to),
  });
  const csv = `/api/v1/reports/profitability.csv?${new URLSearchParams({ from, to, group })}`;
  return (
    <div className="flex flex-col gap-4">
      <section aria-label="Filtros" className="grid gap-3 rounded-xl border border-line bg-surface p-4 sm:grid-cols-4">
        <TextField label="Desde" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
        <TextField label="Hasta" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
        <SelectField
          label="Agrupar por"
          value={group}
          onChange={(e) => setGroup(e.target.value as Group)}
          options={[
            { value: "event", label: "Evento" },
            { value: "client", label: "Cliente" },
            { value: "month", label: "Mes" },
          ]}
        />
        <a
          href={csv}
          className="inline-flex h-11 items-center justify-center gap-2 self-end rounded-lg border border-line px-3 text-sm font-medium hover:bg-subtle sm:h-10"
        >
          <Download className="size-4" aria-hidden /> Descargar CSV
        </a>
      </section>
      <p className="text-xs text-ink-muted">
        Eventos con presupuesto aceptado y fecha en el rango. La ganancia real cuenta solo los eventos con gastos cargados y es
        parcial hasta que el evento se cierra.
      </p>
      {query.isError ? <Notice tone="error">{errorMessage(query.error)}</Notice> : null}
      {query.data ? (
        query.data.rows.length ? (
          <section aria-label="Rentabilidad" className="overflow-x-auto rounded-xl border border-line bg-surface">
            <table className="w-full min-w-[56rem] text-sm tabular-nums">
              <thead className="bg-subtle text-left text-xs uppercase tracking-wide text-ink-muted">
                <tr>
                  <th className="px-3 py-2 font-medium">{group === "event" ? "Evento" : group === "client" ? "Cliente" : "Mes"}</th>
                  <th className="px-3 py-2 text-right font-medium">Eventos</th>
                  <th className="px-3 py-2 text-right font-medium">Venta neta</th>
                  <th className="px-3 py-2 text-right font-medium">Ganancia est.</th>
                  <th className="px-3 py-2 text-right font-medium">Margen est.</th>
                  <th className="px-3 py-2 text-right font-medium">Costo real</th>
                  <th className="px-3 py-2 text-right font-medium">Ganancia real</th>
                  <th className="px-3 py-2 text-right font-medium">Margen real</th>
                  <th className="px-3 py-2 text-right font-medium">Desvío costo</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {query.data.rows.map((row) => (
                  <ReportLine key={row.key} row={row} />
                ))}
                <ReportLine row={query.data.total} total />
              </tbody>
            </table>
          </section>
        ) : (
          <p className="rounded-xl border border-line bg-surface p-4 text-sm text-ink-muted">No hay eventos aprobados con fecha en ese rango.</p>
        )
      ) : query.isPending ? (
        <p className="text-sm text-ink-muted">Cargando…</p>
      ) : null}
    </div>
  );
}
