"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { Notice } from "@/components/ui/notice";
import { PageHeader } from "@/components/ui/page-header";
import { pct } from "@/features/pricing/shared";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import type { CompareOut } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatMoney, formatQuantity } from "@/lib/format/number";

import { BUDGETS_KEY, budgetKey } from "./keys";

const FIELD_LABELS: Record<string, string> = {
  name_internal: "Nombre",
  description_client: "Descripción",
  quantity: "Cantidad",
  days: "Días",
  supplier_name: "Proveedor",
  unit_cost_amount: "Costo unitario",
  unit_cost_includes_iva: "Costo con IVA",
  pricing_mode: "Modo de precio",
  markup_applied: "Markup",
  discount_rate: "Descuento",
  sale_total: "Venta",
  section: "Sección",
};

const MONEY_FIELDS = new Set(["unit_cost_amount", "sale_total"]);
const RATE_FIELDS = new Set(["markup_applied", "discount_rate"]);

function show(field: string, value: string | null): string {
  if (value === null || value === "") return "—";
  if (MONEY_FIELDS.has(field)) return formatMoney(value);
  if (RATE_FIELDS.has(field)) return pct(value);
  if (field === "quantity") return formatQuantity(value);
  if (value === "True" || value === "False") return value === "True" ? "Sí" : "No";
  return value;
}

function Row({ label, before, after, money = true }: { label: string; before: string | null; after: string | null; money?: boolean }) {
  if (before === null || after === null) return null;
  const fmt = money ? formatMoney : (v: string) => pct(v);
  return (
    <div className="flex items-baseline justify-between gap-3 py-1 text-sm">
      <span className="text-ink-muted">{label}</span>
      <span className="tabular-nums">
        {fmt(before)} → <strong>{fmt(after)}</strong>
      </span>
    </div>
  );
}

const KIND: Record<CompareOut["lines"][number]["kind"], { label: string; tone: string }> = {
  ADDED: { label: "Agregado", tone: "bg-success/10 text-success" },
  REMOVED: { label: "Quitado", tone: "bg-danger/10 text-danger" },
  MODIFIED: { label: "Modificado", tone: "bg-accent/10 text-accent" },
};

/** B-10: qué cambió entre dos versiones (ítems y totales). */
export function CompareVersions({ budgetId, from, to }: { budgetId: string; from: number; to: number }) {
  const router = useRouter();
  const budget = useQuery({
    queryKey: budgetKey(budgetId),
    queryFn: async () => unwrap(await api.GET("/api/v1/budgets/{budget_id}", { params: { path: { budget_id: budgetId } } })),
  });
  const diff = useQuery({
    queryKey: [...BUDGETS_KEY, "compare", budgetId, from, to],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/budgets/{budget_id}/compare", {
          params: { path: { budget_id: budgetId }, query: { from, to } },
        }),
      ),
  });
  const versions = budget.data?.versions ?? [];

  function pick(nextFrom: number, nextTo: number) {
    router.replace(`/budgets/${budgetId}/compare?from=${nextFrom}&to=${nextTo}`);
  }

  return (
    <>
      <Link href={`/budgets/${budgetId}`} className="mb-3 inline-flex items-center gap-1 text-sm text-ink-muted hover:text-ink">
        <ArrowLeft className="size-4" aria-hidden /> Volver al presupuesto
      </Link>
      <PageHeader
        title="Comparar versiones"
        description={budget.data ? `#${budget.data.number} · ${budget.data.title}` : undefined}
      />
      <div className="mb-4 flex flex-wrap items-center gap-2 text-sm">
        <select aria-label="Versión anterior" value={from} onChange={(e) => pick(Number(e.target.value), to)} className="h-10 rounded-lg border border-line bg-surface px-2">
          {versions.map((v) => (
            <option key={v.id} value={v.version_no}>
              v{v.version_no}
            </option>
          ))}
        </select>
        <span>→</span>
        <select aria-label="Versión nueva" value={to} onChange={(e) => pick(from, Number(e.target.value))} className="h-10 rounded-lg border border-line bg-surface px-2">
          {versions.map((v) => (
            <option key={v.id} value={v.version_no}>
              v{v.version_no}
            </option>
          ))}
        </select>
      </div>
      {diff.isError ? <Notice tone="error">{errorMessage(diff.error)}</Notice> : null}
      {diff.data ? (
        <div className="flex flex-col gap-4">
          <section aria-label="Resumen" className="rounded-xl border border-line bg-surface p-5">
            <p className="mb-2 text-sm">
              {diff.data.added} agregados · {diff.data.removed} quitados · {diff.data.modified} modificados
              {diff.data.reordered ? <span className="text-ink-muted"> · {diff.data.reordered} cambiaron de orden</span> : null}
            </p>
            <Row label="Venta neta" before={diff.data.sale_net_before} after={diff.data.sale_net_after} />
            <Row label="Total con IVA" before={diff.data.total_before} after={diff.data.total_after} />
            <Row label="Costo" before={diff.data.cost_before} after={diff.data.cost_after} />
            <Row label="Ganancia" before={diff.data.profit_before} after={diff.data.profit_after} />
            <Row label="Margen" before={diff.data.margin_net_before} after={diff.data.margin_net_after} money={false} />
            {diff.data.margin_delta_points ? (
              <p className="text-right text-xs text-ink-muted">
                {diff.data.margin_delta_points.startsWith("-") ? "" : "+"}
                {diff.data.margin_delta_points.replace(".", ",")} puntos de margen
              </p>
            ) : null}
          </section>
          {diff.data.lines.length === 0 ? (
            <Notice>Las dos versiones tienen los mismos ítems.</Notice>
          ) : (
            <ul className="divide-y divide-line rounded-xl border border-line bg-surface">
              {diff.data.lines.map((line) => (
                <li key={line.line_key} className="px-5 py-3">
                  <p className="flex flex-wrap items-center gap-2">
                    <span className={cn("rounded px-1.5 py-0.5 text-xs", KIND[line.kind].tone)}>{KIND[line.kind].label}</span>
                    <span className="font-medium">{line.name}</span>
                    <span className="ml-auto text-sm tabular-nums">
                      {line.sale_before ? formatMoney(line.sale_before) : "—"} → {line.sale_after ? formatMoney(line.sale_after) : "—"}
                    </span>
                  </p>
                  {line.changes.length ? (
                    <ul className="mt-1 text-sm text-ink-muted">
                      {line.changes
                        .filter((c) => c.field !== "sale_total")
                        .map((c) => (
                          <li key={c.field}>
                            {FIELD_LABELS[c.field] ?? c.field}: {show(c.field, c.before)} → <span className="text-ink">{show(c.field, c.after)}</span>
                          </li>
                        ))}
                    </ul>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : (
        <p className="text-sm text-ink-muted">Cargando…</p>
      )}
    </>
  );
}
