"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Star } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { CheckboxField, SelectField, TextAreaField, TextField } from "@/components/ui/field";
import { Notice } from "@/components/ui/notice";
import { PageHeader } from "@/components/ui/page-header";
import { useSession } from "@/features/auth/session";
import { ScopedMarkup } from "@/features/pricing/scoped-markup";
import { PRICING_KEY } from "@/features/pricing/shared";
import { Rating } from "@/features/suppliers/suppliers-list";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import type { ChargeMode, Offer, Product, Schemas } from "@/lib/api/types";
import { formatDay } from "@/lib/format/date";
import { formatMoney, formatQuantity } from "@/lib/format/number";
import { textValue } from "@/lib/form";
import { parseDecimalAR } from "@/lib/parse/number";

import { categoryOptions } from "./category-tree";
import { CostFields, CostFormActions, readCost } from "./cost-form";
import {
  CHARGE_MODE_LABELS,
  CostLabel,
  IVA_OPTIONS,
  PRODUCTS_KEY,
  SUPPLIERS_KEY,
  ivaLabel,
  normalizeRate,
  useCategories,
  useSuppliers,
  useUnits,
} from "./shared";

const productKey = (id: string) => [...PRODUCTS_KEY, "detail", id] as const;

function BackLink() {
  return (
    <Link href="/catalog" className="mb-3 inline-flex items-center gap-1 text-sm text-ink-muted hover:text-ink">
      <ArrowLeft className="size-4" aria-hidden /> Catálogo
    </Link>
  );
}

// --- Datos del producto -------------------------------------------------------------------

type ProductBody = Schemas["ProductIn"];

function ProductEditor({ product }: { product: Product | null }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { can } = useSession();
  const editable = can("catalog.edit");
  const categories = useCategories();
  const units = useUnits();
  const [saved, setSaved] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: async (body: ProductBody) =>
      product
        ? unwrap(await api.PATCH("/api/v1/products/{product_id}", { params: { path: { product_id: product.id } }, body }))
        : unwrap(await api.POST("/api/v1/products", { body })),
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: PRODUCTS_KEY });
      void queryClient.invalidateQueries({ queryKey: PRICING_KEY }); // el rubro define el markup
      queryClient.setQueryData(productKey(data.id), data);
      if (product) setSaved(true);
      else router.replace(`/catalog/${data.id}`);
    },
  });
  const remove = useMutation({
    mutationFn: async (id: string) =>
      unwrap(await api.DELETE("/api/v1/products/{product_id}", { params: { path: { product_id: id } } })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: PRODUCTS_KEY });
      router.replace("/catalog");
    },
  });

  if (!categories.data || !units.data) return <p className="text-sm text-ink-muted">Cargando…</p>;

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        const minRaw = textValue(form, "min_quantity");
        const minQuantity = minRaw === null ? null : parseDecimalAR(minRaw);
        setSaved(false);
        setFormError(null);
        if (minRaw !== null && minQuantity === null) {
          setFormError("La cantidad mínima no es un número válido");
          return;
        }
        save.mutate({
          name: String(form.get("name")).trim(),
          category_id: String(form.get("category_id")),
          unit_id: String(form.get("unit_id")),
          charge_mode: String(form.get("charge_mode")) as ChargeMode,
          iva_rate: textValue(form, "iva_rate"),
          min_quantity: minQuantity,
          description_internal: textValue(form, "description_internal"),
          description_client: textValue(form, "description_client"),
          is_active: product ? form.get("is_active") === "on" : true,
        });
      }}
    >
      <fieldset disabled={!editable} className="grid gap-4 rounded-xl border border-line bg-surface p-5 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <TextField label="Nombre" name="name" required maxLength={200} defaultValue={product?.name} autoFocus={!product} />
        </div>
        <SelectField
          label="Rubro"
          name="category_id"
          required
          options={categoryOptions(categories.data)}
          defaultValue={product?.category_id}
        />
        <SelectField
          label="Unidad"
          name="unit_id"
          options={units.data.map((u) => ({ value: u.id, label: `${u.name} (${u.code})` }))}
          defaultValue={product?.unit_id ?? units.data.find((u) => u.code === "u")?.id}
        />
        <SelectField
          label="Modo de cobro"
          name="charge_mode"
          options={Object.entries(CHARGE_MODE_LABELS).map(([value, label]) => ({ value, label }))}
          defaultValue={product?.charge_mode ?? "FIXED"}
          hint="«Por día» multiplica por los días del evento."
        />
        <SelectField
          label="IVA"
          name="iva_rate"
          options={[{ value: "", label: "El del rubro" }, ...IVA_OPTIONS]}
          defaultValue={product?.iva_rate ? normalizeRate(product.iva_rate) : ""}
        />
        <TextField
          label="Cantidad mínima (opcional)"
          name="min_quantity"
          inputMode="decimal"
          defaultValue={product?.min_quantity ? formatQuantity(product.min_quantity) : ""}
        />
        {product ? (
          <CheckboxField label="Activo (aparece al presupuestar)" name="is_active" defaultChecked={product.is_active} className="sm:mt-6" />
        ) : null}
        <div className="sm:col-span-2">
          <TextAreaField
            label="Descripción para el cliente"
            name="description_client"
            maxLength={5000}
            hint="Es lo que se ve en la propuesta."
            defaultValue={product?.description_client ?? ""}
          />
        </div>
        <div className="sm:col-span-2">
          <TextAreaField
            label="Notas internas"
            name="description_internal"
            maxLength={5000}
            hint="Solo las ve tu equipo."
            defaultValue={product?.description_internal ?? ""}
          />
        </div>
      </fieldset>
      {formError ? <Notice tone="error">{formError}</Notice> : null}
      {save.isError ? <Notice tone="error">{errorMessage(save.error)}</Notice> : null}
      {remove.isError ? <Notice tone="error">{errorMessage(remove.error)}</Notice> : null}
      {saved ? <Notice tone="success">Cambios guardados.</Notice> : null}
      {editable ? (
        <div className="flex flex-wrap justify-between gap-3">
          <Button type="submit" loading={save.isPending}>
            {product ? "Guardar cambios" : "Crear producto"}
          </Button>
          {product ? (
            <Button
              type="button"
              variant="ghost"
              className="text-danger"
              loading={remove.isPending}
              onClick={() => {
                if (window.confirm(`¿Borrar ${product.name}? Los presupuestos que ya lo usan no cambian.`)) {
                  remove.mutate(product.id);
                }
              }}
            >
              Borrar producto
            </Button>
          ) : null}
        </div>
      ) : null}
    </form>
  );
}

// --- Ofertas y costos ------------------------------------------------------------------

function PriceHistory({ offerId }: { offerId: string }) {
  const prices = useQuery({
    queryKey: [...PRODUCTS_KEY, "prices", offerId],
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/offers/{offer_id}/prices", { params: { path: { offer_id: offerId } } })),
  });
  if (prices.isPending) return <p className="text-sm text-ink-muted">Cargando…</p>;
  if (prices.isError) return <Notice tone="error">{errorMessage(prices.error)}</Notice>;
  if (prices.data.length === 0) return <p className="text-sm text-ink-muted">Sin costos cargados.</p>;
  return (
    <ol aria-label="Historial de costos" className="divide-y divide-line rounded-lg border border-line text-sm">
      {prices.data.map((price) => (
        <li key={price.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 px-3 py-2">
          <span className="w-24 tabular-nums text-ink-muted">{formatDay(price.valid_from)}</span>
          <span className="font-medium tabular-nums">{formatMoney(price.amount, price.currency)}</span>
          <span className="text-xs text-ink-muted">
            {price.includes_iva ? "IVA incl." : `+ IVA ${ivaLabel(price.iva_rate)}`}
          </span>
          <span className="w-full text-xs text-ink-muted sm:ml-auto sm:w-auto">
            {[price.source_ref, price.created_by_name].filter(Boolean).join(" · ")}
          </span>
        </li>
      ))}
    </ol>
  );
}

function OfferCard({ offer }: { offer: Offer }) {
  const queryClient = useQueryClient();
  const { can } = useSession();
  const [panel, setPanel] = useState<"cost" | "history" | null>(null);
  const [costError, setCostError] = useState<string | null>(null);

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: PRODUCTS_KEY });
    void queryClient.invalidateQueries({ queryKey: SUPPLIERS_KEY });
  };
  const update = useMutation({
    mutationFn: async (body: Schemas["OfferUpdate"]) =>
      unwrap(await api.PATCH("/api/v1/offers/{offer_id}", { params: { path: { offer_id: offer.id } }, body })),
    onSuccess: refresh,
  });
  const record = useMutation({
    mutationFn: async (body: Schemas["PriceIn"]) =>
      unwrap(await api.POST("/api/v1/offers/{offer_id}/prices", { params: { path: { offer_id: offer.id } }, body })),
    onSuccess: () => {
      setPanel("history");
      refresh();
    },
  });

  return (
    <li className="flex flex-col gap-3 px-5 py-4">
      <div className="flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-2">
            <Link href={`/suppliers/${offer.supplier_id}`} className={offer.is_active ? "font-medium hover:underline" : "font-medium text-ink-muted line-through"}>
              {offer.supplier_name}
            </Link>
            {offer.is_preferred ? (
              <span className="inline-flex items-center gap-1 rounded bg-accent/10 px-1.5 text-xs text-accent">
                <Star className="size-3 fill-current" aria-hidden /> Preferido
              </span>
            ) : null}
            {!offer.is_active ? <span className="rounded bg-subtle px-1.5 text-xs text-ink-muted">Inactiva</span> : null}
            <Rating value={offer.supplier_rating} />
          </p>
          {offer.supplier_sku || offer.notes ? (
            <p className="text-sm text-ink-muted">{[offer.supplier_sku && `Cód. ${offer.supplier_sku}`, offer.notes].filter(Boolean).join(" · ")}</p>
          ) : null}
        </div>
        {can("cost.view") ? (
          <div className="flex flex-col items-start gap-1 sm:items-end">
            <CostLabel cost={offer.current_cost} />
            {offer.upcoming_cost ? (
              <span className="text-xs text-ink-muted">
                Desde {formatDay(offer.upcoming_cost.valid_from)}: {formatMoney(offer.upcoming_cost.amount)}
              </span>
            ) : null}
          </div>
        ) : null}
      </div>
      <div className="flex flex-wrap gap-2">
        {can("costs.edit") && offer.is_active ? (
          <Button size="sm" variant="secondary" onClick={() => setPanel(panel === "cost" ? null : "cost")}>
            Cargar costo
          </Button>
        ) : null}
        {can("cost.view") ? (
          <Button size="sm" variant="ghost" onClick={() => setPanel(panel === "history" ? null : "history")}>
            {panel === "history" ? "Ocultar historial" : "Historial"}
          </Button>
        ) : null}
        {can("catalog.edit") && offer.is_active && !offer.is_preferred ? (
          <Button size="sm" variant="ghost" loading={update.isPending} onClick={() => update.mutate({ is_preferred: true })}>
            Marcar preferido
          </Button>
        ) : null}
        {can("catalog.edit") ? (
          <Button size="sm" variant="ghost" loading={update.isPending} onClick={() => update.mutate({ is_active: !offer.is_active })}>
            {offer.is_active ? "Desactivar" : "Reactivar"}
          </Button>
        ) : null}
      </div>
      {update.isError ? <Notice tone="error">{errorMessage(update.error)}</Notice> : null}
      {panel === "cost" ? (
        <form
          aria-label={`Nuevo costo de ${offer.supplier_name}`}
          className="flex flex-col gap-3 rounded-lg border border-line p-4"
          onSubmit={(event) => {
            event.preventDefault();
            setCostError(null);
            try {
              const cost = readCost(new FormData(event.currentTarget));
              if (cost) record.mutate(cost);
              else setCostError("Ingresá el costo");
            } catch (error) {
              setCostError((error as Error).message);
            }
          }}
        >
          <CostFields />
          {costError ? <Notice tone="error">{costError}</Notice> : null}
          {record.isError ? <Notice tone="error">{errorMessage(record.error)}</Notice> : null}
          <p className="text-xs text-ink-muted">
            El historial no se edita: si te equivocaste, cargá el costo correcto y queda como el vigente.
          </p>
          <CostFormActions loading={record.isPending} onCancel={() => setPanel(null)} />
        </form>
      ) : null}
      {panel === "history" ? <PriceHistory offerId={offer.id} /> : null}
    </li>
  );
}

function AddOffer({ product }: { product: Product }) {
  const queryClient = useQueryClient();
  const { can } = useSession();
  const suppliers = useSuppliers();
  const [open, setOpen] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const add = useMutation({
    mutationFn: async (body: Schemas["OfferIn"]) =>
      unwrap(
        await api.POST("/api/v1/products/{product_id}/offers", { params: { path: { product_id: product.id } }, body }),
      ),
    onSuccess: (data) => {
      queryClient.setQueryData(productKey(product.id), data);
      void queryClient.invalidateQueries({ queryKey: PRODUCTS_KEY });
      void queryClient.invalidateQueries({ queryKey: SUPPLIERS_KEY });
      setOpen(false);
    },
  });
  const taken = new Set(product.offers.map((o) => o.supplier_id));
  const available = (suppliers.data ?? []).filter((s) => !taken.has(s.id));

  if (!open) {
    return (
      <div className="px-5 py-4">
        <Button variant="secondary" size="sm" onClick={() => setOpen(true)}>
          Agregar proveedor
        </Button>
      </div>
    );
  }
  return (
    <form
      aria-label="Agregar proveedor"
      className="flex flex-col gap-3 px-5 py-4"
      onSubmit={(event) => {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        setFormError(null);
        try {
          add.mutate({
            supplier_id: String(form.get("supplier_id")),
            supplier_sku: textValue(form, "supplier_sku"),
            notes: textValue(form, "offer_notes"),
            is_preferred: form.get("is_preferred") === "on",
            cost: can("costs.edit") ? readCost(form) : null,
          });
        } catch (error) {
          setFormError((error as Error).message);
        }
      }}
    >
      {available.length === 0 && suppliers.isSuccess ? (
        <Notice>
          Todos tus proveedores ya ofrecen este producto. <Link href="/suppliers/new" className="underline">Crear un proveedor</Link>
        </Notice>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2">
            <SelectField
              label="Proveedor"
              name="supplier_id"
              required
              options={available.map((s) => ({ value: s.id, label: s.name }))}
            />
            <TextField label="Código del proveedor (opcional)" name="supplier_sku" maxLength={80} />
            <div className="sm:col-span-2">
              <TextField label="Notas (opcional)" name="offer_notes" maxLength={2000} placeholder="Ej.: pedir con 48 h" />
            </div>
            <CheckboxField label="Es el proveedor preferido" name="is_preferred" />
          </div>
          {can("costs.edit") ? (
            <fieldset className="flex flex-col gap-2">
              <legend className="mb-2 text-sm font-medium">Costo (opcional)</legend>
              <CostFields />
            </fieldset>
          ) : null}
          {formError ? <Notice tone="error">{formError}</Notice> : null}
          {add.isError ? <Notice tone="error">{errorMessage(add.error)}</Notice> : null}
          <div className="flex gap-2">
            <Button type="submit" size="sm" loading={add.isPending}>
              Agregar
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setOpen(false)}>
              Cancelar
            </Button>
          </div>
        </>
      )}
    </form>
  );
}

function Offers({ product }: { product: Product }) {
  const { can } = useSession();
  return (
    <section className="mb-4 rounded-xl border border-line bg-surface">
      <div className="border-b border-line px-5 py-3">
        <h2 className="font-semibold">¿Quién lo ofrece?</h2>
        {can("cost.view") ? (
          <p className="text-sm text-ink-muted">De menor a mayor costo vigente. El preferido es el que se usa al presupuestar.</p>
        ) : null}
      </div>
      {product.offers.length === 0 ? (
        <p className="px-5 py-4 text-sm text-ink-muted">Todavía nadie. Agregá el proveedor que te lo cotiza.</p>
      ) : (
        <ul className="divide-y divide-line">
          {product.offers.map((offer) => (
            <OfferCard key={offer.id} offer={offer} />
          ))}
        </ul>
      )}
      {can("catalog.edit") ? (
        <div className="border-t border-line">
          <AddOffer product={product} />
        </div>
      ) : null}
    </section>
  );
}

export function NewProduct() {
  return (
    <>
      <BackLink />
      <PageHeader title="Nuevo producto" description="Después de crearlo, le agregás proveedores y costos." />
      <ProductEditor product={null} />
    </>
  );
}

export function ProductDetail({ id }: { id: string }) {
  const product = useQuery({
    queryKey: productKey(id),
    queryFn: async () => unwrap(await api.GET("/api/v1/products/{product_id}", { params: { path: { product_id: id } } })),
  });
  return (
    <>
      <BackLink />
      {product.isPending ? <p className="text-sm text-ink-muted">Cargando…</p> : null}
      {product.isError ? <Notice tone="error">{errorMessage(product.error)}</Notice> : null}
      {product.data ? (
        <>
          <PageHeader title={product.data.name} description={product.data.is_active ? undefined : "Inactivo: no aparece al presupuestar."} />
          <Offers product={product.data} />
          <ScopedMarkup scope="PRODUCT" scopeId={product.data.id} />
          <h2 className="mb-3 font-semibold">Datos del producto</h2>
          <ProductEditor key={product.data.id} product={product.data} />
        </>
      ) : null}
    </>
  );
}
