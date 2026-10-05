"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { CheckboxField, SelectField, TextField } from "@/components/ui/field";
import type { Schemas } from "@/lib/api/types";
import { todayInArgentina } from "@/lib/format/date";
import { formatMoney } from "@/lib/format/number";
import { parseDecimalAR } from "@/lib/parse/number";

import { IVA_OPTIONS } from "./shared";

export type PriceBody = Schemas["PriceIn"];

/** Campos de un costo. El monto se escribe en formato argentino y viaja como string. */
export function CostFields({ prefix = "" }: { prefix?: string }) {
  const [raw, setRaw] = useState("");
  const parsed = parseDecimalAR(raw);
  const invalid = raw.trim() !== "" && parsed === null;
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <TextField
        label="Costo"
        name={`${prefix}amount`}
        inputMode="decimal"
        autoComplete="off"
        placeholder="Ej.: 150.000"
        value={raw}
        onChange={(e) => setRaw(e.target.value)}
        error={invalid ? "No es un número válido" : undefined}
        hint={parsed !== null ? `Se guarda como ${formatMoney(parsed)}` : "Por unidad, como te lo cotizó el proveedor"}
      />
      <TextField label="Vigente desde" name={`${prefix}valid_from`} type="date" defaultValue={todayInArgentina()} required />
      <SelectField label="Alícuota de IVA" name={`${prefix}iva_rate`} options={IVA_OPTIONS} defaultValue="0.21" />
      <CheckboxField label="El monto ya incluye IVA" name={`${prefix}includes_iva`} className="sm:mt-6" />
      <div className="sm:col-span-2">
        <TextField
          label="Referencia (opcional)"
          name={`${prefix}source_ref`}
          maxLength={200}
          placeholder="Ej.: presupuesto 1234 del 02/10"
        />
      </div>
    </div>
  );
}

/** Lee los campos de `CostFields`. `null` si no se cargó monto; lanza si el monto es inválido. */
export function readCost(form: FormData, prefix = ""): PriceBody | null {
  const raw = String(form.get(`${prefix}amount`) ?? "");
  if (raw.trim() === "") return null;
  const amount = parseDecimalAR(raw);
  if (amount === null) throw new Error("El costo no es un número válido");
  const sourceRef = String(form.get(`${prefix}source_ref`) ?? "").trim();
  return {
    amount,
    includes_iva: form.get(`${prefix}includes_iva`) === "on",
    iva_rate: String(form.get(`${prefix}iva_rate`) ?? "0.21"),
    valid_from: String(form.get(`${prefix}valid_from`) || todayInArgentina()),
    source_ref: sourceRef || null,
  };
}

export function CostFormActions({ loading, onCancel }: { loading: boolean; onCancel: () => void }) {
  return (
    <div className="flex gap-2">
      <Button type="submit" size="sm" loading={loading}>
        Guardar costo
      </Button>
      <Button type="button" size="sm" variant="ghost" onClick={onCancel}>
        Cancelar
      </Button>
    </div>
  );
}
