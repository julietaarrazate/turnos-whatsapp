"use client";

import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import { formatMoney, formatPercentCompact } from "@/lib/format/number";

/** Historial comercial calculado (no cargado a mano), PRODUCT_SPEC §4.2. */
export function ClientHistory({ id }: { id: string }) {
  const history = useQuery({
    queryKey: ["clients", "history", id],
    queryFn: async () => unwrap(await api.GET("/api/v1/clients/{client_id}/history", { params: { path: { client_id: id } } })),
  });
  const h = history.data;
  if (!h) return null;
  const preferential =
    h.preferential_markup !== null
      ? `${formatPercentCompact(h.preferential_markup)} (${h.preferential_mode === "MARGIN" ? "margen" : "markup"} del cliente)`
      : null;
  return (
    <section aria-label="Historial comercial" className="mb-4 rounded-xl border border-line bg-surface p-5 text-sm">
      <h2 className="mb-2 font-semibold">Historial comercial</h2>
      <p>
        {h.budgets} presupuesto{h.budgets === 1 ? "" : "s"} · {h.accepted} aceptado{h.accepted === 1 ? "" : "s"} · {h.lost} perdido
        {h.lost === 1 ? "" : "s"}
        {h.conversion !== null ? ` · conversión ${formatPercentCompact(h.conversion)}` : ""}
      </p>
      <dl className="mt-3 grid gap-x-6 gap-y-1 sm:grid-cols-[auto_1fr]">
        <dt className="text-ink-muted">Facturado histórico (aceptado, sin IVA)</dt>
        <dd className="tabular-nums">{formatMoney(h.billed)}</dd>
        {h.estimated_margin !== null ? (
          <>
            <dt className="text-ink-muted">Margen promedio estimado / real</dt>
            <dd className="tabular-nums">
              {formatPercentCompact(h.estimated_margin)} / {h.actual_margin !== null ? formatPercentCompact(h.actual_margin) : "—"}
            </dd>
          </>
        ) : null}
        {preferential ? (
          <>
            <dt className="text-ink-muted">Markup preferencial</dt>
            <dd>{preferential}</dd>
          </>
        ) : null}
      </dl>
    </section>
  );
}
