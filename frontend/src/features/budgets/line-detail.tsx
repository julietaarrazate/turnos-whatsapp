"use client";

import { useQuery } from "@tanstack/react-query";
import { Lock, Trash2, X } from "lucide-react";
import { useEffect, useRef } from "react";

import { Button } from "@/components/ui/button";
import { CheckboxField, SelectField } from "@/components/ui/field";
import { useSession } from "@/features/auth/session";
import { CostLabel, IVA_OPTIONS, normalizeRate } from "@/features/catalog/shared";
import { pct } from "@/features/pricing/shared";
import { api, unwrap } from "@/lib/api/client";
import type { BudgetLine, BudgetVersion, LineUpdate } from "@/lib/api/types";
import { formatDay } from "@/lib/format/date";
import { formatMoney } from "@/lib/format/number";

import { CommitField } from "./commit-field";
import { daysField, moneyField, optionalPercentField, percentField, quantityField } from "./format";

const SOURCE_LABELS: Record<string, string> = {
  LINE: "manual",
  VERSION: "del presupuesto",
  CLIENT: "del cliente",
  PRODUCT: "del producto",
  CATEGORY: "del rubro",
  ORG: "general",
  TARGET_MARGIN: "por margen objetivo",
  TARGET_PRICE: "por precio objetivo",
};

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs text-ink-muted">{label}</span>
      {children}
    </div>
  );
}

/** Panel lateral (desktop) o bottom sheet (mobile) con todo el detalle de una línea. */
export function LineDetail({
  line,
  version,
  editable,
  onClose,
  onUpdate,
  onDelete,
}: {
  line: BudgetLine;
  version: BudgetVersion;
  editable: boolean;
  onClose: () => void;
  onUpdate: (body: LineUpdate) => void;
  onDelete: () => void;
}) {
  const { can } = useSession();
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    dialog.current?.showModal();
  }, []);
  const offers = useQuery({
    queryKey: ["products", "detail", line.product_id],
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/products/{product_id}", { params: { path: { product_id: line.product_id ?? "" } } })),
    enabled: Boolean(line.product_id) && editable && can("cost.view"),
  });
  const cost = line.cost;
  const margin = line.margin;
  const canOverride = can("budget.markup_override");

  return (
    <dialog
      ref={dialog}
      aria-label={`Detalle de ${line.name_internal}`}
      onClose={onClose}
      onClick={(e) => e.target === dialog.current && dialog.current?.close()}
      className="m-0 mt-auto max-h-[90dvh] w-full max-w-none overflow-y-auto rounded-t-2xl border-0 bg-surface p-0 backdrop:bg-ink/30 lg:mt-0 lg:ml-auto lg:h-dvh lg:max-h-none lg:w-[28rem] lg:rounded-none lg:border-l lg:border-line"
    >
      <div className="sticky top-0 flex items-start gap-3 border-b border-line bg-surface px-5 py-4">
        <div className="min-w-0 flex-1">
          <h2 className="font-semibold">{line.name_internal}</h2>
          <p className="text-sm text-ink-muted">
            {[line.category_name, line.supplier_name, `por ${line.unit_code}`].filter(Boolean).join(" · ")}
          </p>
        </div>
        <button type="button" aria-label="Cerrar" onClick={() => dialog.current?.close()} className="rounded p-1 hover:bg-subtle">
          <X className="size-5" aria-hidden />
        </button>
      </div>

      <fieldset disabled={!editable} className="flex flex-col gap-5 px-5 py-4">
        <div className="grid grid-cols-2 gap-3">
          <CommitField label="Cantidad" hideLabel={false} value={line.quantity} {...quantityField} onCommit={(quantity) => onUpdate({ quantity })} />
          {line.charge_mode === "PER_DAY" ? (
            <CommitField label="Días" hideLabel={false} value={line.days} {...daysField} inputMode="numeric" onCommit={(days) => onUpdate({ days })} />
          ) : (
            <Field label="Cobro">
              <span className="h-9 text-sm leading-9">Precio fijo</span>
            </Field>
          )}
        </div>
        <SelectField
          label="Modo de cobro"
          value={line.charge_mode}
          onChange={(e) => onUpdate({ charge_mode: e.target.value as BudgetLine["charge_mode"] })}
          options={[
            { value: "FIXED", label: "Precio fijo" },
            { value: "PER_DAY", label: "Por día (× días)" },
          ]}
        />

        {cost ? (
          <section className="flex flex-col gap-3 rounded-lg border border-line p-3">
            <h3 className="text-sm font-medium">Costo</h3>
            {offers.data && offers.data.offers.length > 1 ? (
              <SelectField
                label="Proveedor"
                value={cost.supplier_product_id ?? ""}
                onChange={(e) => onUpdate({ offer_id: e.target.value })}
                options={offers.data.offers
                  .filter((o) => o.is_active)
                  .map((o) => ({
                    value: o.id,
                    label: `${o.supplier_name}${o.current_cost ? ` · ${formatMoney(o.current_cost.amount)}` : ""}`,
                  }))}
              />
            ) : null}
            <div className="grid grid-cols-2 gap-3">
              <CommitField
                label="Costo unitario"
                hideLabel={false}
                value={cost.unit_cost_amount}
                {...moneyField}
                onCommit={(unit_cost_amount) => onUpdate({ unit_cost_amount })}
              />
              <SelectField
                label="IVA del costo"
                value={normalizeRate(cost.unit_cost_iva_rate)}
                onChange={(e) => onUpdate({ unit_cost_iva_rate: e.target.value })}
                options={IVA_OPTIONS}
              />
            </div>
            <CheckboxField
              label="El costo ya incluye IVA"
              checked={cost.unit_cost_includes_iva}
              onChange={(e) => onUpdate({ unit_cost_includes_iva: e.target.checked })}
            />
            <p className="text-xs text-ink-muted">
              Costo de la línea: <span className="font-medium text-ink">{formatMoney(cost.cost_total)}</span>
              {cost.cost_as_of ? ` · precio del ${formatDay(cost.cost_as_of)}` : " · cargado a mano"}
              {cost.cost_stale ? <span className="text-warning"> · desactualizado ({cost.cost_days_old} días)</span> : null}
            </p>
          </section>
        ) : null}

        {margin ? (
          <section className="flex flex-col gap-3 rounded-lg border border-line p-3">
            <h3 className="text-sm font-medium">Precio</h3>
            <SelectField
              label="Cómo se calcula"
              value={line.pricing_mode}
              onChange={(e) => {
                const mode = e.target.value as BudgetLine["pricing_mode"];
                if (mode === "MARGIN") onUpdate({ pricing_mode: mode, target_margin: margin.target_margin ?? "0.25" });
                else if (mode === "PRICE") onUpdate({ pricing_mode: mode, target_price: line.target_price ?? line.sale_list_total });
                else onUpdate({ pricing_mode: mode });
              }}
              options={[
                { value: "MARKUP", label: "Markup sobre el costo" },
                { value: "MARGIN", label: "Margen objetivo" },
                { value: "PRICE", label: "Precio fijo de venta" },
              ]}
            />
            {line.pricing_mode === "MARKUP" ? (
              <CommitField
                label={`Markup manual (vacío = ${pct(margin.rule_markup)} ${SOURCE_LABELS[margin.rule_source]})`}
                hideLabel={false}
                value={margin.markup_manual}
                {...optionalPercentField}
                suffix="%"
                placeholder={pct(margin.rule_markup).replace(" %", "")}
                disabled={!canOverride}
                onCommit={(markup_manual) => onUpdate({ markup_manual })}
              />
            ) : null}
            {line.pricing_mode === "MARGIN" ? (
              <CommitField
                label="Margen objetivo"
                hideLabel={false}
                value={margin.target_margin ?? "0"}
                {...percentField}
                suffix="%"
                onCommit={(target_margin) => onUpdate({ target_margin })}
              />
            ) : null}
            {line.pricing_mode === "PRICE" ? (
              <CommitField
                label="Precio de venta de la línea (sin IVA)"
                hideLabel={false}
                value={line.target_price ?? "0"}
                {...moneyField}
                onCommit={(target_price) => onUpdate({ target_price })}
              />
            ) : null}
            <CommitField
              label="Descuento de la línea"
              hideLabel={false}
              value={line.discount_rate}
              {...percentField}
              suffix="%"
              onCommit={(discount_rate) => onUpdate({ discount_rate })}
            />
            <p className="text-xs text-ink-muted">
              Markup aplicado: {margin.markup_applied ? pct(margin.markup_applied) : "—"}
              {margin.markup_source ? ` (${SOURCE_LABELS[margin.markup_source]})` : ""} · ganancia {formatMoney(margin.profit)} ·
              margen {margin.margin ? pct(margin.margin) : "—"}
            </p>
            {version.pricing_mode === "PRICE" || version.pricing_mode === "MARGIN" ? (
              <CheckboxField
                label="Bloquear: no la toca el modo del presupuesto"
                checked={line.is_locked}
                onChange={(e) => onUpdate({ is_locked: e.target.checked })}
              />
            ) : null}
          </section>
        ) : null}

        <section className="flex flex-col gap-3">
          <SelectField
            label="IVA de la venta"
            value={normalizeRate(line.iva_rate)}
            onChange={(e) => onUpdate({ iva_rate: e.target.value })}
            options={IVA_OPTIONS}
          />
          <SelectField
            label="Sección"
            value={line.section_id}
            onChange={(e) => onUpdate({ section_id: e.target.value })}
            options={version.sections.map((s) => ({ value: s.id, label: s.title_client }))}
          />
          <label className="flex flex-col gap-1">
            <span className="text-xs text-ink-muted">Descripción para el cliente</span>
            <textarea
              defaultValue={line.description_client ?? ""}
              rows={3}
              maxLength={5000}
              onBlur={(e) => {
                const value = e.target.value.trim() || null;
                if (value !== (line.description_client ?? null)) onUpdate({ description_client: value });
              }}
              className="rounded-lg border border-line bg-surface px-3 py-2 text-base sm:text-sm"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-ink-muted">Notas internas</span>
            <textarea
              defaultValue={line.notes_internal ?? ""}
              rows={2}
              maxLength={5000}
              onBlur={(e) => {
                const value = e.target.value.trim() || null;
                if (value !== (line.notes_internal ?? null)) onUpdate({ notes_internal: value });
              }}
              className="rounded-lg border border-line bg-surface px-3 py-2 text-base sm:text-sm"
            />
          </label>
          <CheckboxField
            label="Se ve en la propuesta"
            checked={line.show_on_proposal}
            onChange={(e) => onUpdate({ show_on_proposal: e.target.checked })}
          />
        </section>
        {line.product_id && cost && offers.data ? (
          <p className="text-xs text-ink-muted">
            En el catálogo hoy:{" "}
            <CostLabel cost={offers.data.offers.find((o) => o.id === cost.supplier_product_id)?.current_cost ?? null} compact />
          </p>
        ) : null}
      </fieldset>

      <div className="sticky bottom-0 flex items-center justify-between gap-3 border-t border-line bg-surface px-5 py-3">
        <p className="text-sm">
          Venta: <span className="font-semibold tabular-nums">{formatMoney(line.sale_total)}</span>
          {line.is_locked ? <Lock className="ml-1 inline size-3.5 text-ink-muted" aria-label="Bloqueada" /> : null}
        </p>
        {editable ? (
          <Button
            variant="ghost"
            size="sm"
            className="text-danger"
            onClick={() => {
              onDelete();
              dialog.current?.close();
            }}
          >
            <Trash2 className="size-4" aria-hidden /> Quitar
          </Button>
        ) : null}
      </div>
    </dialog>
  );
}
