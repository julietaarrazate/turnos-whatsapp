"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { SelectField, TextField } from "@/components/ui/field";
import { Notice } from "@/components/ui/notice";
import { PageHeader } from "@/components/ui/page-header";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import type { Schemas } from "@/lib/api/types";
import { formatDay } from "@/lib/format/date";
import { formatMoney } from "@/lib/format/number";
import { percentToFraction } from "@/lib/parse/percent";

import { CATALOG_KEY, useCategories, useSuppliers } from "./shared";

/** C-10: "Proveedor X subió 8 % desde el 1/11". Simula antes de aplicar. */
export function BulkIncrease() {
  const queryClient = useQueryClient();
  const suppliers = useSuppliers();
  const categories = useCategories();
  const [supplierId, setSupplierId] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [percent, setPercent] = useState("");
  const [validFrom, setValidFrom] = useState("");
  // "8" → "0.08"; "-5" → "-0.05" (sobre el string, sin floats).
  const negative = percent.trim().startsWith("-");
  const magnitude = percentToFraction(percent.trim().replace(/^-/, ""));
  const rate = magnitude === null ? null : negative && magnitude !== "0" ? `-${magnitude}` : magnitude;
  const body = (): Schemas["BulkIncreaseIn"] => ({
    supplier_id: supplierId || null,
    category_id: categoryId || null,
    rate: rate ?? "0",
    valid_from: validFrom || null,
    note: null,
  });
  const preview = useMutation({
    mutationFn: async () => unwrap(await api.POST("/api/v1/catalog/bulk-increase/preview", { body: body() })),
  });
  const apply = useMutation({
    mutationFn: async () => unwrap(await api.POST("/api/v1/catalog/bulk-increase", { body: body() })),
    onSuccess: () => {
      preview.reset();
      void queryClient.invalidateQueries({ queryKey: CATALOG_KEY });
    },
  });
  const ready = Boolean((supplierId || categoryId) && rate && rate !== "0");
  return (
    <>
      <PageHeader title="Aumento masivo" description="Un costo nuevo para cada oferta, desde la fecha que elijas. Lo ya enviado no cambia." />
      <form
        aria-label="Aumento masivo"
        className="mb-4 grid gap-4 rounded-xl border border-line bg-surface p-5 sm:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          apply.reset();
          preview.mutate();
        }}
      >
        <SelectField
          label="Proveedor"
          value={supplierId}
          onChange={(e) => setSupplierId(e.target.value)}
          options={[{ value: "", label: "Todos" }, ...(suppliers.data ?? []).map((s) => ({ value: s.id, label: s.name }))]}
        />
        <SelectField
          label="Categoría"
          value={categoryId}
          onChange={(e) => setCategoryId(e.target.value)}
          options={[{ value: "", label: "Todas" }, ...(categories.data ?? []).map((c) => ({ value: c.id, label: c.name }))]}
        />
        <TextField
          label="Aumento (%)"
          inputMode="decimal"
          value={percent}
          onChange={(e) => setPercent(e.target.value)}
          hint="Ej.: 8 · para una baja, -5."
          error={percent && rate === null ? "Revisá el porcentaje" : undefined}
        />
        <TextField label="Vigente desde" type="date" value={validFrom} onChange={(e) => setValidFrom(e.target.value)} hint="Vacío: hoy." />
        <div className="sm:col-span-2">
          <Button type="submit" variant="secondary" disabled={!ready} loading={preview.isPending}>
            Simular
          </Button>
        </div>
      </form>
      {preview.isError ? <Notice tone="error">{errorMessage(preview.error)}</Notice> : null}
      {apply.isError ? <Notice tone="error">{errorMessage(apply.error)}</Notice> : null}
      {apply.data ? (
        <Notice tone="success">
          Listo: {apply.data.items.length} costos nuevos desde el {formatDay(apply.data.valid_from)} ({apply.data.scope}).{" "}
          <Link href="/catalog" className="underline">
            Ver catálogo
          </Link>
        </Notice>
      ) : null}
      {preview.data ? (
        <section aria-label="Simulación" className="rounded-xl border border-line bg-surface">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-3">
            <p className="text-sm">
              <strong>{preview.data.items.length}</strong> ofertas · {preview.data.scope} · desde {formatDay(preview.data.valid_from)}
              {preview.data.skipped_without_cost ? ` · ${preview.data.skipped_without_cost} sin costo (no cambian)` : ""}
            </p>
            <Button size="sm" disabled={!preview.data.items.length} loading={apply.isPending} onClick={() => apply.mutate()}>
              Aplicar aumento
            </Button>
          </div>
          <ul className="divide-y divide-line text-sm">
            {preview.data.items.map((item) => (
              <li key={item.offer_id} className="flex flex-wrap items-baseline gap-x-3 px-4 py-2">
                <span className="min-w-0 flex-1">
                  {item.product_name} <span className="text-ink-muted">· {item.supplier_name}</span>
                </span>
                <span className="tabular-nums text-ink-muted">{formatMoney(item.current)}</span>
                <span aria-hidden>→</span>
                <span className="font-medium tabular-nums">{formatMoney(item.new)}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </>
  );
}
