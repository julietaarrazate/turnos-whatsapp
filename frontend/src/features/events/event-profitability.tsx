"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { Notice } from "@/components/ui/notice";
import { EVENTS_KEY } from "@/features/budgets/keys";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import type { Schemas } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatMoney, formatPercentCompact } from "@/lib/format/number";

type Result = Schemas["ResultOut"];

export const profitabilityKey = (id: string) => [...EVENTS_KEY, "profitability", id] as const;

function signedPercent(rate: string): string {
  return rate.startsWith("-") ? `−${formatPercentCompact(rate.slice(1))}` : `+${formatPercentCompact(rate)}`;
}

const ROWS: { key: keyof Result; label: string }[] = [
  { key: "sale_net", label: "Venta neta" },
  { key: "cost", label: "Costo" },
  { key: "sale_charges", label: "Cargos sobre la venta" },
  { key: "profit", label: "Ganancia" },
];

/** Pestaña Rentabilidad: estimada (versión aceptada) vs real (gastos), O-06 / journey J7. */
export function EventProfitability({ id }: { id: string }) {
  const query = useQuery({
    queryKey: profitabilityKey(id),
    queryFn: async () => unwrap(await api.GET("/api/v1/events/{event_id}/profitability", { params: { path: { event_id: id } } })),
  });
  if (query.isPending) return <p className="text-sm text-ink-muted">Cargando…</p>;
  if (query.isError) return <Notice tone="error">{errorMessage(query.error)}</Notice>;
  const data = query.data;
  if (!data.estimated || !data.actual) {
    return <Notice tone="info">El evento todavía no tiene un presupuesto aprobado: la rentabilidad sale de la versión aceptada.</Notice>;
  }
  const { estimated, actual } = data;
  const worse = actual.margin !== null && estimated.margin !== null && Number(actual.margin) < Number(estimated.margin);
  return (
    <div className="flex flex-col gap-4">
      {data.final ? (
        <Notice tone="success">Evento cerrado: la rentabilidad real es final.</Notice>
      ) : (
        <Notice tone="info">
          Parcial: el evento no está cerrado y pueden faltar gastos ({data.expenses_count} cargados).{" "}
          <Link href={`/events/${id}/expenses`} className="underline">
            Ver gastos
          </Link>
        </Notice>
      )}
      <section aria-label="Rentabilidad" className="overflow-hidden rounded-xl border border-line bg-surface">
        <table className="w-full text-sm">
          <thead className="bg-subtle text-left text-xs uppercase tracking-wide text-ink-muted">
            <tr>
              <th className="px-4 py-2 font-medium" />
              <th className="px-4 py-2 text-right font-medium">Estimado</th>
              <th className="px-4 py-2 text-right font-medium">Real{data.final ? "" : " (parcial)"}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line tabular-nums">
            {ROWS.map((row) => (
              <tr key={row.key}>
                <th scope="row" className="px-4 py-2.5 text-left font-normal">
                  {row.label}
                </th>
                <td className="px-4 py-2.5 text-right">{formatMoney(String(estimated[row.key]))}</td>
                <td className="px-4 py-2.5 text-right">{formatMoney(String(actual[row.key]))}</td>
              </tr>
            ))}
            <tr className="font-semibold">
              <th scope="row" className="px-4 py-2.5 text-left">
                Margen
              </th>
              <td className="px-4 py-2.5 text-right">{estimated.margin ? formatPercentCompact(estimated.margin) : "—"}</td>
              <td className={cn("px-4 py-2.5 text-right", worse ? "text-danger" : "text-success")}>
                {actual.margin ? formatPercentCompact(actual.margin) : "—"}
              </td>
            </tr>
          </tbody>
        </table>
      </section>
      {data.cost_delta !== null && data.cost_delta_rate !== null ? (
        <p className="text-sm text-ink-muted">
          Desvío de costo: {data.cost_delta.startsWith("-") ? "−" : "+"}
          {formatMoney(data.cost_delta.replace("-", ""))} ({signedPercent(data.cost_delta_rate)})
        </p>
      ) : null}
    </div>
  );
}
