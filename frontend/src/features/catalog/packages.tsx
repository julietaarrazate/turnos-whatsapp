"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { CheckboxField, SelectField, TextField } from "@/components/ui/field";
import { Notice } from "@/components/ui/notice";
import { PageHeader } from "@/components/ui/page-header";
import { useSession } from "@/features/auth/session";
import { ProductSearch } from "@/features/budgets/product-search";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import type { Schemas } from "@/lib/api/types";
import { parseDecimalAR } from "@/lib/parse/number";

type Item = Schemas["PackageItemIn"] & { product_name: string; quantity_text: string };
type Draft = { id: string | null; name: string; description: string; is_active: boolean; items: Item[] };

const PACKAGES_KEY = ["packages"] as const;
const EMPTY: Draft = { id: null, name: "", description: "", is_active: true, items: [] };
const DAYS_RULES = [
  { value: "EVENT_DAYS", label: "Días del evento" },
  { value: "SETUP_DAYS", label: "Días de armado" },
  { value: "FIXED", label: "Días fijos" },
];

function fromPackage(p: Schemas["PackageOut"]): Draft {
  return {
    id: p.id,
    name: p.name,
    description: p.description ?? "",
    is_active: p.is_active,
    items: p.items.map((i) => ({
      product_id: i.product_id,
      product_name: i.product_name,
      quantity: i.quantity,
      quantity_text: i.quantity.replace(/\.?0+$/, "").replace(".", ","),
      days_rule: i.days_rule,
      fixed_days: i.fixed_days,
      section_title: i.section_title,
      description_client_override: i.description_client_override,
    })),
  };
}

function Editor({ initial, onDone }: { initial: Draft; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState(initial);
  const save = useMutation({
    mutationFn: async () => {
      const body: Schemas["PackageIn"] = {
        name: draft.name.trim(),
        description: draft.description.trim() || null,
        is_active: draft.is_active,
        items: draft.items.map((i) => ({
          product_id: i.product_id,
          quantity: parseDecimalAR(i.quantity_text) ?? "1",
          days_rule: i.days_rule,
          fixed_days: i.days_rule === "FIXED" ? (i.fixed_days ?? 1) : null,
          section_title: i.section_title?.trim() || null,
          description_client_override: i.description_client_override?.trim() || null,
        })),
      };
      return draft.id
        ? unwrap(await api.PUT("/api/v1/packages/{package_id}", { params: { path: { package_id: draft.id } }, body }))
        : unwrap(await api.POST("/api/v1/packages", { body }));
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: PACKAGES_KEY });
      onDone();
    },
  });
  const update = (index: number, patch: Partial<Item>) =>
    setDraft((d) => ({ ...d, items: d.items.map((item, i) => (i === index ? { ...item, ...patch } : item)) }));
  const invalid = !draft.name.trim() || !draft.items.length || draft.items.some((i) => !parseDecimalAR(i.quantity_text));
  return (
    <form
      aria-label={draft.id ? `Editar ${initial.name}` : "Nuevo paquete"}
      className="mb-4 flex flex-col gap-4 rounded-xl border border-line bg-surface p-5"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <TextField label="Nombre" required maxLength={200} value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} placeholder="Ej.: Stand corporativo 6×3" />
        <TextField label="Descripción (opcional)" maxLength={2000} value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} />
      </div>
      <ul className="flex flex-col gap-3">
        {draft.items.map((item, index) => (
          <li key={`${item.product_id}-${index}`} className="grid gap-2 rounded-lg border border-line p-3 sm:grid-cols-[1fr_6rem_10rem_6rem_1fr_auto] sm:items-end">
            <p className="text-sm font-medium sm:self-center">{item.product_name}</p>
            <TextField label={`Cantidad de ${item.product_name}`} hideLabel={false} inputMode="decimal" value={item.quantity_text} onChange={(e) => update(index, { quantity_text: e.target.value })} />
            <SelectField label="Días" value={item.days_rule ?? "EVENT_DAYS"} onChange={(e) => update(index, { days_rule: e.target.value })} options={DAYS_RULES} />
            {item.days_rule === "FIXED" ? (
              <TextField label="N.º de días" type="number" min={1} max={365} value={item.fixed_days ?? 1} onChange={(e) => update(index, { fixed_days: Number(e.target.value) || 1 })} />
            ) : (
              <span />
            )}
            <TextField label="Sección (opcional)" maxLength={200} value={item.section_title ?? ""} onChange={(e) => update(index, { section_title: e.target.value })} />
            <Button type="button" variant="ghost" size="sm" aria-label={`Quitar ${item.product_name}`} onClick={() => setDraft((d) => ({ ...d, items: d.items.filter((_, i) => i !== index) }))}>
              <Trash2 className="size-4" aria-hidden />
            </Button>
          </li>
        ))}
      </ul>
      <ProductSearch
        onPick={(product) =>
          setDraft((d) => ({
            ...d,
            items: [
              ...d.items,
              { product_id: product.id, product_name: product.name, quantity: "1", quantity_text: "1", days_rule: "EVENT_DAYS", fixed_days: null, section_title: null, description_client_override: null },
            ],
          }))
        }
      />
      <p className="text-xs text-ink-muted">Los días solo cuentan para los productos que cobran por día. Sin sección, el ítem va a la sección donde se inserta el paquete.</p>
      <CheckboxField label="Activo (aparece al presupuestar)" checked={draft.is_active} onChange={(e) => setDraft({ ...draft, is_active: e.target.checked })} />
      {save.isError ? <Notice tone="error">{errorMessage(save.error)}</Notice> : null}
      <div className="flex gap-2">
        <Button type="submit" disabled={invalid} loading={save.isPending}>
          Guardar paquete
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancelar
        </Button>
      </div>
    </form>
  );
}

/** B-06: paquetes / plantillas del catálogo. */
export function Packages() {
  const { can } = useSession();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<Draft | null>(null);
  const packages = useQuery({ queryKey: PACKAGES_KEY, queryFn: async () => unwrap(await api.GET("/api/v1/packages")) });
  const open = useMutation({
    mutationFn: async (id: string) => unwrap(await api.GET("/api/v1/packages/{package_id}", { params: { path: { package_id: id } } })),
    onSuccess: (data) => setEditing(fromPackage(data)),
  });
  const remove = useMutation({
    mutationFn: async (id: string) => unwrap(await api.DELETE("/api/v1/packages/{package_id}", { params: { path: { package_id: id } } })),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: PACKAGES_KEY }),
  });
  const editable = can("catalog.edit");
  return (
    <>
      <PageHeader
        title="Paquetes"
        description="Plantillas de productos que se insertan juntas en un presupuesto."
        actions={
          editable && !editing ? (
            <Button onClick={() => setEditing(EMPTY)}>
              <Plus className="size-4" aria-hidden /> Nuevo paquete
            </Button>
          ) : null
        }
      />
      {editing ? <Editor key={editing.id ?? "new"} initial={editing} onDone={() => setEditing(null)} /> : null}
      {packages.isError ? <Notice tone="error">{errorMessage(packages.error)}</Notice> : null}
      <section aria-label="Lista de paquetes" className="rounded-xl border border-line bg-surface">
        {packages.data?.length ? (
          <ul className="divide-y divide-line">
            {packages.data.map((p) => (
              <li key={p.id} className="flex flex-wrap items-center gap-3 px-4 py-3 text-sm">
                <span className="min-w-0 flex-1">
                  <span className="font-medium">{p.name}</span>
                  <span className="text-ink-muted">
                    {" "}
                    · {p.item_count} ítems{p.is_active ? "" : " · inactivo"}
                  </span>
                </span>
                {editable ? (
                  <>
                    <Button size="sm" variant="secondary" loading={open.isPending && open.variables === p.id} onClick={() => open.mutate(p.id)}>
                      Editar
                    </Button>
                    <Button size="sm" variant="ghost" aria-label={`Borrar ${p.name}`} onClick={() => window.confirm(`¿Borrar el paquete ${p.name}?`) && remove.mutate(p.id)}>
                      <Trash2 className="size-4" aria-hidden />
                    </Button>
                  </>
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="px-4 py-3 text-sm text-ink-muted">{packages.isPending ? "Cargando…" : "Todavía no hay paquetes."}</p>
        )}
      </section>
    </>
  );
}
