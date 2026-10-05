"use client";

import { useState } from "react";

import { SelectField } from "@/components/ui/field";
import type { Budget, BudgetVersion, VersionUpdate } from "@/lib/api/types";
import { formatDay } from "@/lib/format/date";
import { formatMoney } from "@/lib/format/number";

import { CommitField } from "./commit-field";
import { moneyField, optionalPercentField, percentField } from "./format";

const MODES = [
  { value: "LINE", label: "Cada ítem con su markup" },
  { value: "MARKUP", label: "Un markup para todo" },
  { value: "MARGIN", label: "Margen objetivo" },
  { value: "PRICE", label: "Precio objetivo (el cliente tiene $X)" },
];

/** Modo de pricing del presupuesto (§5.5), descuento global y moneda. */
export function VersionSettings({
  budget,
  version,
  editable,
  onUpdate,
}: {
  budget: Budget;
  version: BudgetVersion;
  editable: boolean;
  onUpdate: (body: VersionUpdate) => void;
}) {
  const [open, setOpen] = useState(false);
  const margins = version.margins;
  const summary = MODES.find((m) => m.value === version.pricing_mode)?.label;
  return (
    <section className="mb-4 rounded-xl border border-line bg-surface">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left text-sm"
      >
        <span>
          <span className="font-medium">Cálculo del precio:</span> {summary}
          {version.global_discount_rate !== "0.000000" ? " · con descuento" : ""}
          {budget.currency === "USD" ? " · en dólares" : ""}
        </span>
        <span className="text-ink-muted">{open ? "Cerrar" : "Cambiar"}</span>
      </button>
      {open ? (
        <fieldset disabled={!editable} className="grid gap-4 border-t border-line px-4 py-4 sm:grid-cols-2">
          {margins ? (
            <SelectField
              label="Modo"
              value={version.pricing_mode}
              onChange={(e) => {
                const mode = e.target.value as BudgetVersion["pricing_mode"];
                if (mode === "PRICE") onUpdate({ pricing_mode: mode, target_price: version.target_price ?? version.sale_net, global_discount_rate: "0" });
                else if (mode === "MARGIN") onUpdate({ pricing_mode: mode, target_margin: margins.target_margin ?? "0.25" });
                else onUpdate({ pricing_mode: mode });
              }}
              options={MODES}
            />
          ) : null}
          {margins && version.pricing_mode === "MARKUP" ? (
            <CommitField
              label="Markup para todos los ítems"
              hideLabel={false}
              value={margins.markup_override}
              {...optionalPercentField}
              suffix="%"
              onCommit={(markup_override) => onUpdate({ markup_override })}
            />
          ) : null}
          {margins && version.pricing_mode === "MARGIN" ? (
            <CommitField
              label="Margen objetivo"
              hideLabel={false}
              value={margins.target_margin ?? "0"}
              {...percentField}
              suffix="%"
              onCommit={(target_margin) => onUpdate({ target_margin })}
            />
          ) : null}
          {version.pricing_mode === "PRICE" ? (
            <CommitField
              label={version.target_includes_iva ? "Precio objetivo (con IVA)" : "Precio objetivo (sin IVA)"}
              hideLabel={false}
              value={version.target_price ?? "0"}
              {...moneyField}
              onCommit={(target_price) => onUpdate({ target_price })}
            />
          ) : (
            <CommitField
              label="Descuento global"
              hideLabel={false}
              value={version.global_discount_rate}
              {...percentField}
              suffix="%"
              onCommit={(global_discount_rate) => onUpdate({ global_discount_rate })}
            />
          )}
          <SelectField
            label="Moneda de la propuesta"
            value={budget.currency}
            onChange={(e) => onUpdate({ currency: e.target.value as Budget["currency"] })}
            options={[
              { value: "ARS", label: "Pesos" },
              { value: "USD", label: "Dólares" },
            ]}
            hint={
              version.fx
                ? `US$ 1 = ${formatMoney(version.fx.rate)} del ${formatDay(version.fx.rate_date)} (congelado en esta versión)`
                : undefined
            }
          />
          {version.fx ? (
            <button
              type="button"
              onClick={() => onUpdate({ refresh_fx: true })}
              className="self-end text-left text-sm text-accent underline"
            >
              Actualizar al último tipo de cambio cargado
            </button>
          ) : null}
        </fieldset>
      ) : null}
    </section>
  );
}
