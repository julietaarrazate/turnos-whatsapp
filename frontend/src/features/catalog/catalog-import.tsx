"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FileSpreadsheet } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { SelectField } from "@/components/ui/field";
import { Notice } from "@/components/ui/notice";
import { PageHeader } from "@/components/ui/page-header";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import type { Schemas } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatMoney } from "@/lib/format/number";

import { CATALOG_KEY } from "./shared";

type Field = Schemas["ImportField"];
type Mapping = Record<string, number | null>;

const FIELDS: { key: Field; label: string; required?: boolean }[] = [
  { key: "name", label: "Producto", required: true },
  { key: "category", label: "Categoría" },
  { key: "supplier", label: "Proveedor" },
  { key: "unit", label: "Unidad" },
  { key: "cost", label: "Costo" },
  { key: "includes_iva", label: "¿Incluye IVA?" },
  { key: "iva_rate", label: "Alícuota de IVA" },
  { key: "charge_mode", label: "Cobro (por día)" },
  { key: "description_client", label: "Descripción para el cliente" },
  { key: "supplier_sku", label: "Código del proveedor" },
];

const ACTIONS: Record<string, { label: string; tone: string }> = {
  CREATE: { label: "Nuevo", tone: "text-success" },
  UPDATE: { label: "Existe", tone: "text-ink-muted" },
  ERROR: { label: "Error", tone: "text-danger" },
};

async function toBase64(file: File): Promise<string> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}

/** C-09: importar el catálogo desde Excel o CSV, con mapeo, vista previa y confirmación. */
export function CatalogImport() {
  const queryClient = useQueryClient();
  const [file, setFile] = useState<{ name: string; base64: string } | null>(null);
  const [mapping, setMapping] = useState<Mapping>({});
  const body = (next: Mapping = mapping): Schemas["CatalogImportIn"] | null =>
    file ? { file_base64: file.base64, filename: file.name, mapping: next, sheet: null, valid_from: null } : null;
  const preview = useMutation({
    mutationFn: async (payload: Schemas["CatalogImportIn"]) => unwrap(await api.POST("/api/v1/catalog/import/preview", { body: payload })),
    onSuccess: (data) => setMapping(data.mapping),
  });
  const apply = useMutation({
    mutationFn: async (payload: Schemas["CatalogImportIn"]) => unwrap(await api.POST("/api/v1/catalog/import", { body: payload })),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: CATALOG_KEY }),
  });
  const data = apply.data ?? preview.data;
  return (
    <>
      <PageHeader
        title="Importar catálogo"
        description="Tu Excel o CSV de productos y costos: elegís qué columna es cada dato, revisás y confirmás."
      />
      <section className="mb-4 flex flex-wrap items-center gap-3 rounded-xl border border-line bg-surface p-5">
        <label className="flex cursor-pointer items-center gap-2 rounded-lg border border-dashed border-line px-4 py-3 text-sm hover:bg-subtle">
          <FileSpreadsheet className="size-5 text-accent" aria-hidden />
          <span>{file ? file.name : "Elegir archivo .xlsx o .csv"}</span>
          <input
            type="file"
            accept=".xlsx,.csv"
            aria-label="Planilla del catálogo"
            className="sr-only"
            onChange={async (e) => {
              const chosen = e.currentTarget.files?.[0];
              e.currentTarget.value = "";
              if (!chosen) return;
              const next = { name: chosen.name, base64: await toBase64(chosen) };
              setFile(next);
              setMapping({});
              apply.reset();
              preview.mutate({ file_base64: next.base64, filename: next.name, mapping: null, sheet: null, valid_from: null });
            }}
          />
        </label>
        {preview.isPending ? <span className="text-sm text-ink-muted">Leyendo…</span> : null}
      </section>
      {preview.isError ? <Notice tone="error">{errorMessage(preview.error)}</Notice> : null}
      {apply.isError ? <Notice tone="error">{errorMessage(apply.error)}</Notice> : null}
      {data && file ? (
        <div className="flex flex-col gap-4">
          {apply.data ? (
            <Notice tone="success">
              Importado: {apply.data.summary.valid} filas · {apply.data.summary.products_new} productos nuevos ·{" "}
              {apply.data.summary.suppliers_new} proveedores nuevos · {apply.data.summary.costs} costos cargados.{" "}
              <Link href="/catalog" className="underline">
                Ver catálogo
              </Link>
            </Notice>
          ) : null}
          <section aria-label="Columnas" className="grid gap-3 rounded-xl border border-line bg-surface p-5 sm:grid-cols-2 lg:grid-cols-3">
            <h2 className="font-semibold sm:col-span-2 lg:col-span-3">Qué columna es cada dato</h2>
            {FIELDS.map((f) => (
              <SelectField
                key={f.key}
                label={f.required ? `${f.label} *` : f.label}
                value={mapping[f.key] ?? ""}
                onChange={(e) => {
                  const next = { ...mapping, [f.key]: e.target.value === "" ? null : Number(e.target.value) };
                  setMapping(next);
                  const payload = body(next);
                  if (payload) preview.mutate(payload);
                }}
                options={[
                  { value: "", label: "— No está —" },
                  ...data.headers.map((h, i) => ({ value: String(i), label: h || `Columna ${i + 1}` })),
                ]}
              />
            ))}
          </section>
          <section aria-label="Vista previa" className="rounded-xl border border-line bg-surface">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-3">
              <p className="text-sm">
                {data.summary.rows} filas · <strong>{data.summary.valid} para importar</strong>
                {data.summary.errors ? <span className="text-danger"> · {data.summary.errors} con errores (no se importan)</span> : null}
                {" · "}
                {data.summary.products_new} productos nuevos · {data.summary.suppliers_new} proveedores nuevos ·{" "}
                {data.summary.categories_new} categorías nuevas
              </p>
              {apply.data ? null : (
                <Button
                  size="sm"
                  disabled={!data.summary.valid}
                  loading={apply.isPending}
                  onClick={() => {
                    const payload = body();
                    if (payload) apply.mutate(payload);
                  }}
                >
                  Importar {data.summary.valid} filas
                </Button>
              )}
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[40rem] text-sm">
                <thead className="bg-subtle text-left text-xs uppercase tracking-wide text-ink-muted">
                  <tr>
                    <th className="px-3 py-2 font-medium">Fila</th>
                    <th className="px-3 py-2 font-medium">Producto</th>
                    <th className="px-3 py-2 font-medium">Proveedor</th>
                    <th className="px-3 py-2 text-right font-medium">Costo</th>
                    <th className="px-3 py-2 font-medium">Estado</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {data.rows.map((row) => (
                    <tr key={row.row}>
                      <td className="px-3 py-2 text-ink-muted">{row.row}</td>
                      <td className="px-3 py-2">
                        {row.name ?? "—"}
                        {row.category ? <span className="text-ink-muted"> · {row.category}</span> : null}
                      </td>
                      <td className="px-3 py-2">{row.supplier ?? "—"}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{row.cost !== null ? formatMoney(row.cost) : "—"}</td>
                      <td className={cn("px-3 py-2", ACTIONS[row.action]?.tone)}>
                        {row.errors.length ? row.errors.join(" · ") : ACTIONS[row.action]?.label}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      ) : null}
    </>
  );
}
