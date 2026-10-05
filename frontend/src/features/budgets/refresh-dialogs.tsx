"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Notice } from "@/components/ui/notice";
import { useSession } from "@/features/auth/session";
import { pct } from "@/features/pricing/shared";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import type { Budget, Schemas } from "@/lib/api/types";
import { formatDay } from "@/lib/format/date";
import { formatMoney } from "@/lib/format/number";

import { BUDGETS_KEY } from "./keys";
import type { BudgetEditor } from "./use-budget-editor";

const previewKey = (budgetId: string, kind: string, lock: number) => [...BUDGETS_KEY, "preview", kind, budgetId, lock] as const;

function Delta({ totals }: { totals: Schemas["TotalsDelta"] }) {
  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-1 rounded-lg bg-subtle px-3 py-2 text-sm">
      <dt className="text-ink-muted">Venta neta</dt>
      <dd className="text-right tabular-nums">
        {formatMoney(totals.sale_net_before)} → <strong>{formatMoney(totals.sale_net_after)}</strong>
      </dd>
      {totals.profit_before !== null && totals.profit_after !== null ? (
        <>
          <dt className="text-ink-muted">Ganancia</dt>
          <dd className="text-right tabular-nums">
            {formatMoney(totals.profit_before ?? "0")} → <strong>{formatMoney(totals.profit_after ?? "0")}</strong>
          </dd>
          <dt className="text-ink-muted">Margen</dt>
          <dd className="text-right tabular-nums">
            {totals.margin_net_before ? pct(totals.margin_net_before) : "—"} →{" "}
            <strong>{totals.margin_net_after ? pct(totals.margin_net_after) : "—"}</strong>
          </dd>
        </>
      ) : null}
    </dl>
  );
}

function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => ref.current?.showModal(), []);
  return (
    <dialog
      ref={ref}
      aria-label={title}
      onClose={onClose}
      className="m-auto w-[min(36rem,calc(100vw-2rem))] rounded-xl border border-line bg-surface p-0 shadow-2xl backdrop:bg-ink/30"
    >
      <div className="flex flex-col gap-4 p-5">
        <h2 className="text-lg font-semibold">{title}</h2>
        {children}
        <div className="flex justify-end">
          <Button variant="ghost" size="sm" onClick={() => ref.current?.close()}>
            Cerrar
          </Button>
        </div>
      </div>
    </dialog>
  );
}

/** B-08: banner de "costos más nuevos" + diálogo con la vista previa y la elección de líneas. */
export function CostsBanner({ budget, editor }: { budget: Budget; editor: BudgetEditor }) {
  const { can } = useSession();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [skipped, setSkipped] = useState<Set<string>>(new Set());
  const version = budget.version;
  const enabled = can("cost.view") && can("budget.edit") && version.status === "DRAFT";
  const preview = useQuery({
    queryKey: previewKey(budget.id, "costs", version.lock_version),
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/budgets/{budget_id}/draft/refresh-costs", { params: { path: { budget_id: budget.id } } })),
    enabled,
    staleTime: 60_000,
  });
  const changes = preview.data?.changes ?? [];
  if (!enabled || changes.length === 0) return null;

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-3 rounded-xl border border-warning/30 bg-warning/10 px-4 py-3 text-sm">
        <RefreshCw className="size-4 text-warning" aria-hidden />
        <span className="flex-1">
          {changes.length === 1 ? "Hay 1 costo más nuevo" : `Hay ${changes.length} costos más nuevos`} en el catálogo.
        </span>
        <Button size="sm" variant="secondary" onClick={() => setOpen(true)}>
          Revisar y actualizar
        </Button>
      </div>
      {open && preview.data ? (
        <Modal title="Actualizar costos" onClose={() => setOpen(false)}>
          <ul className="flex max-h-72 flex-col divide-y divide-line overflow-y-auto rounded-lg border border-line">
            {changes.map((c) => (
              <li key={c.line_id}>
                <label className="flex items-center gap-3 px-3 py-2 text-sm">
                  <input
                    type="checkbox"
                    className="size-4 accent-accent"
                    checked={!skipped.has(c.line_id)}
                    onChange={(e) => {
                      const next = new Set(skipped);
                      if (e.target.checked) next.delete(c.line_id);
                      else next.add(c.line_id);
                      setSkipped(next);
                    }}
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">{c.name}</span>
                    <span className="block text-xs text-ink-muted">
                      {c.supplier_name ?? ""} · vigente desde {formatDay(c.new_as_of)}
                    </span>
                  </span>
                  <span className="text-right tabular-nums">
                    {formatMoney(c.old_unit_cost)} → <strong>{formatMoney(c.new_unit_cost)}</strong>
                  </span>
                </label>
              </li>
            ))}
          </ul>
          {skipped.size === 0 ? <Delta totals={preview.data.totals} /> : (
            <p className="text-xs text-ink-muted">El total cambia según los ítems que elijas.</p>
          )}
          <Button
            onClick={() => {
              const lineIds = changes.map((c) => c.line_id).filter((id) => !skipped.has(id));
              void editor
                .run((lock) =>
                  api
                    .POST("/api/v1/budgets/{budget_id}/draft/refresh-costs", {
                      params: { path: { budget_id: budget.id }, header: { "If-Match": lock } },
                      body: { line_ids: lineIds },
                    })
                    .then(unwrap),
                )
                .then(() => {
                  setOpen(false);
                  void queryClient.invalidateQueries({ queryKey: [...BUDGETS_KEY, "preview"] });
                });
            }}
          >
            Actualizar {changes.length - skipped.size} {changes.length - skipped.size === 1 ? "costo" : "costos"}
          </Button>
        </Modal>
      ) : null}
    </>
  );
}

/** "Re-aplicar reglas": markups, cargos y redondeo de hoy, con vista previa del efecto. */
export function ReapplyRules({ budget, editor }: { budget: Budget; editor: BudgetEditor }) {
  const { can } = useSession();
  const [open, setOpen] = useState(false);
  const version = budget.version;
  const preview = useQuery({
    queryKey: previewKey(budget.id, "rules", version.lock_version),
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/budgets/{budget_id}/draft/reapply-rules", { params: { path: { budget_id: budget.id } } })),
    enabled: open,
  });
  if (!can("margin.view") || !can("budget.edit") || version.status !== "DRAFT") return null;
  const data = preview.data;
  const chargesChanged = data && JSON.stringify(data.charges_before) !== JSON.stringify(data.charges_after);

  return (
    <>
      <Button variant="ghost" size="sm" onClick={() => setOpen(true)}>
        Re-aplicar reglas
      </Button>
      {open ? (
        <Modal title="Re-aplicar reglas de pricing" onClose={() => setOpen(false)}>
          {preview.isPending ? <p className="text-sm text-ink-muted">Calculando…</p> : null}
          {preview.isError ? <Notice tone="error">{errorMessage(preview.error)}</Notice> : null}
          {data ? (
            <>
              {data.changes.length === 0 && !chargesChanged ? (
                <Notice>El presupuesto ya usa las reglas vigentes.</Notice>
              ) : null}
              {data.changes.length ? (
                <ul className="flex max-h-60 flex-col divide-y divide-line overflow-y-auto rounded-lg border border-line text-sm">
                  {data.changes.map((c) => (
                    <li key={c.line_id} className="flex items-center gap-3 px-3 py-2">
                      <span className="min-w-0 flex-1 truncate">
                        {c.name}
                        {c.has_manual_markup ? <span className="text-xs text-ink-muted"> (tiene markup manual)</span> : null}
                      </span>
                      <span className="tabular-nums">
                        {pct(c.old_markup)} → <strong>{pct(c.new_markup)}</strong>
                      </span>
                    </li>
                  ))}
                </ul>
              ) : null}
              {chargesChanged ? (
                <p className="text-sm">
                  Cargos sobre la venta:{" "}
                  {data.charges_before.map((c) => `${c.name} ${pct(c.rate)}`).join(", ") || "ninguno"} →{" "}
                  <strong>{data.charges_after.map((c) => `${c.name} ${pct(c.rate)}`).join(", ") || "ninguno"}</strong>
                </p>
              ) : null}
              <Delta totals={data.totals} />
              <Button
                disabled={data.changes.length === 0 && !chargesChanged}
                onClick={() =>
                  void editor
                    .run((lock) =>
                      api
                        .POST("/api/v1/budgets/{budget_id}/draft/reapply-rules", {
                          params: { path: { budget_id: budget.id }, header: { "If-Match": lock } },
                        })
                        .then(unwrap),
                    )
                    .then(() => setOpen(false))
                }
              >
                Aplicar
              </Button>
            </>
          ) : null}
        </Modal>
      ) : null}
    </>
  );
}
