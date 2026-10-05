"use client";

import { ChevronRight, Plus, Star } from "lucide-react";
import Link from "next/link";
import { useDeferredValue, useState } from "react";

import { buttonClasses } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Notice } from "@/components/ui/notice";
import { PageHeader } from "@/components/ui/page-header";
import { SearchBox } from "@/components/ui/search-box";
import { useSession } from "@/features/auth/session";
import { useSuppliers } from "@/features/catalog/shared";
import { errorMessage } from "@/lib/api/client";

export function Rating({ value }: { value: number | null }) {
  if (!value) return null;
  return (
    <span className="inline-flex items-center gap-0.5 text-xs text-ink-muted" aria-label={`Calificación ${value} de 5`}>
      <Star className="size-3 fill-current" aria-hidden />
      {value}
    </span>
  );
}

export function SuppliersList() {
  const { can } = useSession();
  const [search, setSearch] = useState("");
  const q = useDeferredValue(search.trim());
  const suppliers = useSuppliers(q);

  return (
    <>
      <PageHeader
        title="Proveedores"
        description="Quién te provee cada rubro, sus contactos y lo que te ofrece."
        actions={
          can("catalog.edit") ? (
            <Link href="/suppliers/new" className={buttonClasses()}>
              <Plus className="size-4" aria-hidden /> Nuevo proveedor
            </Link>
          ) : null
        }
      />
      <div className="mb-4 flex">
        <SearchBox value={search} onChange={setSearch} label="Buscar por nombre o CUIT" />
      </div>
      {suppliers.isError ? <Notice tone="error">{errorMessage(suppliers.error)}</Notice> : null}
      {suppliers.isPending ? <p className="text-sm text-ink-muted">Cargando…</p> : null}
      {suppliers.data?.length === 0 ? (
        <EmptyState title="No hay proveedores que coincidan">Probá con otra búsqueda.</EmptyState>
      ) : null}
      {suppliers.data?.length ? (
        <ul className="divide-y divide-line rounded-xl border border-line bg-surface">
          {suppliers.data.map((supplier) => (
            <li key={supplier.id}>
              <Link href={`/suppliers/${supplier.id}`} className="flex items-center gap-3 px-4 py-3 hover:bg-subtle">
                <div className="min-w-0 flex-1">
                  <p className="flex items-center gap-2 truncate font-medium">
                    {supplier.name}
                    {supplier.is_internal ? (
                      <span className="rounded bg-subtle px-1.5 text-xs font-normal text-ink-muted">Interno</span>
                    ) : null}
                    <Rating value={supplier.rating} />
                  </p>
                  <p className="truncate text-sm text-ink-muted">
                    {supplier.category_names.join(", ") || "Sin rubros"} ·{" "}
                    {supplier.offers_count === 1 ? "1 producto" : `${supplier.offers_count} productos`}
                  </p>
                </div>
                <ChevronRight className="size-4 text-ink-muted" aria-hidden />
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
    </>
  );
}
