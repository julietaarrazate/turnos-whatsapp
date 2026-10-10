"use client";

import { useMutation } from "@tanstack/react-query";
import { FileSpreadsheet, X } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { SelectField } from "@/components/ui/field";
import { Notice } from "@/components/ui/notice";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import type { Schemas } from "@/lib/api/types";
import { toBase64 } from "@/lib/files";
import { formatMoney, formatPercentCompact, formatQuantity } from "@/lib/format/number";

export type SheetChoice = { file_base64: string; sheet: string; title_hint: string };

const LABELS: Record<NonNullable<Schemas["ImportLineOut"]["price_label"]>, string> = {
  BONIFICADO: "Bonificado",
  A_DEFINIR: "A definir",
};

function Preview({ data }: { data: Schemas["ImportPreviewOut"] }) {
  return (
    <details className="rounded-lg border border-line">
      <summary className="cursor-pointer px-3 py-2 text-sm font-medium">Ver lo que se va a importar</summary>
      <div className="flex flex-col gap-3 border-t border-line px-3 py-3 text-sm">
        {data.sections.map((section) => (
          <section key={section.title} aria-label={`Rubro ${section.title}`}>
            <h3 className="font-medium">{section.title}</h3>
            <ul className="divide-y divide-line">
              {section.lines.map((line, index) => (
                <li key={`${line.name}-${index}`} className="flex flex-wrap items-baseline gap-x-3 py-1.5">
                  <span className="min-w-0 flex-1">
                    {line.name}
                    <span className="text-ink-muted">
                      {" "}
                      · {formatQuantity(line.quantity)}
                      {line.days > 1 ? ` × ${line.days} jornadas` : ""}
                    </span>
                  </span>
                  <span className="tabular-nums">{line.price_label ? LABELS[line.price_label] : formatMoney(line.sale_total)}</span>
                  <span className="w-full text-xs text-ink-muted sm:w-auto">
                    Costo {formatMoney(line.cost_amount)}
                    {line.cost_is_total ? " (toda la línea)" : " c/u"}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </details>
  );
}

/**
 * B-01 desde la planilla de la productora: se sube el .xlsx, se elige la hoja y se ve qué se va a
 * importar (rubros, ítems, costos de la META, fee) antes de crear el presupuesto.
 */
export function SheetImport({ value, onChange }: { value: SheetChoice | null; onChange: (value: SheetChoice | null) => void }) {
  const [fileName, setFileName] = useState<string | null>(null);
  const preview = useMutation({
    mutationFn: async (body: Schemas["SheetImportIn"]) => unwrap(await api.POST("/api/v1/budgets/import/preview", { body })),
    onSuccess: (data, body) => onChange({ file_base64: body.file_base64, sheet: data.sheet, title_hint: data.title_hint }),
    onError: () => onChange(null),
  });
  const data = value ? preview.data : undefined;

  return (
    <section aria-label="Importar desde una planilla" className="flex flex-col gap-3 rounded-xl border border-line bg-surface p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="font-semibold">Importar desde una planilla (opcional)</h2>
          <p className="text-sm text-ink-muted">
            Tu Excel de presupuesto: rubros con detalle, Q, jornadas y precio, y la META con proveedor y costos.
          </p>
        </div>
        {value ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => {
              setFileName(null);
              preview.reset();
              onChange(null);
            }}
          >
            <X className="size-4" aria-hidden /> Quitar planilla
          </Button>
        ) : null}
      </div>
      {value === null ? (
        <label className="flex cursor-pointer items-center gap-2 self-start rounded-lg border border-dashed border-line px-4 py-3 text-sm hover:bg-subtle">
          <FileSpreadsheet className="size-5 text-accent" aria-hidden />
          <span>{preview.isPending ? "Leyendo la planilla…" : "Elegir archivo .xlsx"}</span>
          <input
            type="file"
            accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            aria-label="Planilla de presupuesto (.xlsx)"
            className="sr-only"
            onChange={async (e) => {
              const file = e.currentTarget.files?.[0];
              e.currentTarget.value = "";
              if (!file) return;
              setFileName(file.name);
              preview.mutate({ file_base64: await toBase64(file), sheet: null });
            }}
          />
        </label>
      ) : null}
      {preview.isError ? <Notice tone="error">{errorMessage(preview.error)}</Notice> : null}
      {value && data ? (
        <>
          {data.sheets.length > 1 ? (
            <SelectField
              label="Hoja"
              value={value.sheet}
              onChange={(e) => preview.mutate({ file_base64: value.file_base64, sheet: e.target.value })}
              options={data.sheets.map((sheet) => ({ value: sheet, label: sheet }))}
            />
          ) : null}
          <p className="text-sm" role="status">
            <strong>{fileName ?? "Planilla"}</strong> · hoja «{data.sheet}»: {data.line_count} ítems en {data.sections.length} rubros ·
            subtotal {formatMoney(data.subtotal)}
            {data.management_fee_rate !== "0.000000" ? ` · fee de gestión ${formatPercentCompact(data.management_fee_rate)}` : ""}
          </p>
          {data.warnings.length ? (
            <ul className="flex flex-col gap-1 rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-sm">
              {data.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          ) : null}
          {data.notes.length ? (
            <div className="text-sm">
              <p className="text-ink-muted">Notas de la planilla (pasalas a la propuesta: forma de pago y condiciones):</p>
              <ul className="list-inside list-disc">
                {data.notes.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
            </div>
          ) : null}
          <Preview data={data} />
        </>
      ) : null}
    </section>
  );
}
