"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ChevronRight } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ContactsEditor, contactsPayload, newContactKey, type ContactDraft } from "@/components/business/contacts-editor";
import { TAX_CONDITION_OPTIONS } from "@/components/business/tax";
import { Button } from "@/components/ui/button";
import { SelectField, TextAreaField, TextField } from "@/components/ui/field";
import { Notice } from "@/components/ui/notice";
import { PageHeader } from "@/components/ui/page-header";
import { useSession } from "@/features/auth/session";
import { categoryTree } from "@/features/catalog/category-tree";
import { CostLabel, PRODUCTS_KEY, SUPPLIERS_KEY, useCategories } from "@/features/catalog/shared";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import type { Supplier, TaxCondition } from "@/lib/api/types";
import { textValue } from "@/lib/form";

const RATING_OPTIONS = [
  { value: "", label: "Sin calificar" },
  ...[5, 4, 3, 2, 1].map((n) => ({ value: String(n), label: "★".repeat(n) })),
];

function BackLink() {
  return (
    <Link href="/suppliers" className="mb-3 inline-flex items-center gap-1 text-sm text-ink-muted hover:text-ink">
      <ArrowLeft className="size-4" aria-hidden /> Proveedores
    </Link>
  );
}

function CategoryPicker({ selected, onChange }: { selected: string[]; onChange: (ids: string[]) => void }) {
  const categories = useCategories();
  return (
    <fieldset>
      <legend className="mb-2 text-sm font-medium text-ink">Rubros</legend>
      <div className="grid gap-1 sm:grid-cols-2">
        {categoryTree(categories.data ?? []).map(({ category, depth }) => (
          <label key={category.id} className="flex min-h-9 items-center gap-2 text-sm" style={{ paddingLeft: depth * 20 }}>
            <input
              type="checkbox"
              className="size-4 accent-accent"
              checked={selected.includes(category.id)}
              onChange={(e) =>
                onChange(e.target.checked ? [...selected, category.id] : selected.filter((id) => id !== category.id))
              }
            />
            {category.name}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function SupplierEditor({ supplier }: { supplier: Supplier | null }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { can } = useSession();
  const editable = can("catalog.edit");
  const [saved, setSaved] = useState(false);
  const [contacts, setContacts] = useState<ContactDraft[]>(
    () => supplier?.contacts.map((c) => ({ ...c, key: newContactKey() })) ?? [],
  );
  const [categoryIds, setCategoryIds] = useState<string[]>(supplier?.category_ids ?? []);

  type Body = Omit<Supplier, "id" | "contacts" | "offers" | "is_internal"> & {
    contacts: ReturnType<typeof contactsPayload>;
  };
  const save = useMutation({
    mutationFn: async (body: Body) =>
      supplier
        ? unwrap(
            await api.PATCH("/api/v1/suppliers/{supplier_id}", { params: { path: { supplier_id: supplier.id } }, body }),
          )
        : unwrap(await api.POST("/api/v1/suppliers", { body })),
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: SUPPLIERS_KEY });
      queryClient.setQueryData([...SUPPLIERS_KEY, "detail", data.id], data);
      if (supplier) setSaved(true);
      else router.replace(`/suppliers/${data.id}`);
    },
  });
  const remove = useMutation({
    mutationFn: async (id: string) =>
      unwrap(await api.DELETE("/api/v1/suppliers/{supplier_id}", { params: { path: { supplier_id: id } } })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: SUPPLIERS_KEY });
      void queryClient.invalidateQueries({ queryKey: PRODUCTS_KEY });
      router.replace("/suppliers");
    },
  });

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        const rating = textValue(form, "rating");
        setSaved(false);
        save.mutate({
          name: String(form.get("name")).trim(),
          legal_name: textValue(form, "legal_name"),
          tax_id: textValue(form, "tax_id"),
          tax_condition: textValue(form, "tax_condition") as TaxCondition | null,
          payment_terms: textValue(form, "payment_terms"),
          rating: rating ? Number(rating) : null,
          rating_notes: textValue(form, "rating_notes"),
          notes: textValue(form, "notes"),
          category_ids: categoryIds,
          contacts: contactsPayload(contacts),
        });
      }}
    >
      <fieldset disabled={!editable} className="flex flex-col gap-4">
        <section className="grid gap-4 rounded-xl border border-line bg-surface p-5 sm:grid-cols-2">
          <TextField label="Nombre" name="name" required maxLength={200} defaultValue={supplier?.name} autoFocus={!supplier} />
          <TextField label="Razón social" name="legal_name" maxLength={200} defaultValue={supplier?.legal_name ?? ""} />
          <TextField
            label="CUIT"
            name="tax_id"
            inputMode="numeric"
            pattern="\d{2}-?\d{8}-?\d"
            hint="11 dígitos, con o sin guiones"
            defaultValue={supplier?.tax_id ?? ""}
          />
          <SelectField
            label="Condición frente al IVA"
            name="tax_condition"
            options={TAX_CONDITION_OPTIONS}
            defaultValue={supplier?.tax_condition ?? ""}
          />
          <TextField
            label="Condiciones de pago"
            name="payment_terms"
            maxLength={200}
            placeholder="Ej.: 50 % anticipo, saldo a 30 días"
            defaultValue={supplier?.payment_terms ?? ""}
          />
          <SelectField
            label="Calificación"
            name="rating"
            options={RATING_OPTIONS}
            defaultValue={supplier?.rating ? String(supplier.rating) : ""}
          />
          <div className="sm:col-span-2">
            <TextAreaField
              label="Notas de la calificación"
              name="rating_notes"
              rows={2}
              maxLength={2000}
              defaultValue={supplier?.rating_notes ?? ""}
            />
          </div>
          <div className="sm:col-span-2">
            <TextAreaField label="Notas" name="notes" maxLength={5000} defaultValue={supplier?.notes ?? ""} />
          </div>
        </section>
        <section className="rounded-xl border border-line bg-surface p-5">
          <CategoryPicker selected={categoryIds} onChange={setCategoryIds} />
        </section>
        <section className="rounded-xl border border-line bg-surface p-5">
          <ContactsEditor contacts={contacts} onChange={setContacts} />
        </section>
      </fieldset>
      {save.isError ? <Notice tone="error">{errorMessage(save.error)}</Notice> : null}
      {remove.isError ? <Notice tone="error">{errorMessage(remove.error)}</Notice> : null}
      {saved ? <Notice tone="success">Cambios guardados.</Notice> : null}
      {editable ? (
        <div className="flex flex-wrap justify-between gap-3">
          <Button type="submit" loading={save.isPending}>
            {supplier ? "Guardar cambios" : "Crear proveedor"}
          </Button>
          {supplier && !supplier.is_internal ? (
            <Button
              type="button"
              variant="ghost"
              className="text-danger"
              loading={remove.isPending}
              onClick={() => {
                if (window.confirm(`¿Borrar a ${supplier.name}? Sus ofertas quedan inactivas.`)) remove.mutate(supplier.id);
              }}
            >
              Borrar proveedor
            </Button>
          ) : null}
        </div>
      ) : null}
    </form>
  );
}

function SupplierOffers({ supplier }: { supplier: Supplier }) {
  return (
    <section className="mb-4 rounded-xl border border-line bg-surface">
      <h2 className="border-b border-line px-5 py-3 font-semibold">Qué ofrece</h2>
      {supplier.offers.length === 0 ? (
        <p className="px-5 py-4 text-sm text-ink-muted">
          Todavía no tiene productos. Se agregan desde la ficha de cada producto del catálogo.
        </p>
      ) : (
        <ul className="divide-y divide-line">
          {supplier.offers.map((offer) => (
            <li key={offer.offer_id}>
              <Link href={`/catalog/${offer.product_id}`} className="flex items-center gap-3 px-5 py-3 hover:bg-subtle">
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">{offer.product_name}</p>
                  <p className="text-sm text-ink-muted">por {offer.unit_code}</p>
                </div>
                <CostLabel cost={offer.current_cost} compact />
                <ChevronRight className="size-4 text-ink-muted" aria-hidden />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function NewSupplier() {
  return (
    <>
      <BackLink />
      <PageHeader title="Nuevo proveedor" />
      <SupplierEditor supplier={null} />
    </>
  );
}

export function SupplierDetail({ id }: { id: string }) {
  const supplier = useQuery({
    queryKey: [...SUPPLIERS_KEY, "detail", id],
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/suppliers/{supplier_id}", { params: { path: { supplier_id: id } } })),
  });
  return (
    <>
      <BackLink />
      {supplier.isPending ? <p className="text-sm text-ink-muted">Cargando…</p> : null}
      {supplier.isError ? <Notice tone="error">{errorMessage(supplier.error)}</Notice> : null}
      {supplier.data ? (
        <>
          <PageHeader
            title={supplier.data.name}
            description={supplier.data.is_internal ? "Proveedor interno: tu propio equipo y personal." : undefined}
          />
          <SupplierOffers supplier={supplier.data} />
          <SupplierEditor key={supplier.data.id} supplier={supplier.data} />
        </>
      ) : null}
    </>
  );
}
