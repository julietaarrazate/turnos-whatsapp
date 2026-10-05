"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import { ChevronRight, Plus } from "lucide-react";
import Link from "next/link";
import { useDeferredValue, useState } from "react";

import { Button, buttonClasses } from "@/components/ui/button";
import { CheckboxField } from "@/components/ui/field";
import { EmptyState } from "@/components/ui/empty-state";
import { Notice } from "@/components/ui/notice";
import { PageHeader } from "@/components/ui/page-header";
import { SearchBox } from "@/components/ui/search-box";
import { useSession } from "@/features/auth/session";
import { api, errorMessage, unwrap } from "@/lib/api/client";

import { categoryOptions } from "./category-tree";
import { CHARGE_MODE_LABELS, CostLabel, PRODUCTS_KEY, useCategories } from "./shared";

export function ProductsList() {
  const { can } = useSession();
  const showCost = can("cost.view");
  const [search, setSearch] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [includeInactive, setIncludeInactive] = useState(false);
  const q = useDeferredValue(search.trim());
  const categories = useCategories();
  const products = useInfiniteQuery({
    queryKey: [...PRODUCTS_KEY, "list", q, categoryId, includeInactive],
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam }) =>
      unwrap(
        await api.GET("/api/v1/products", {
          params: {
            query: {
              q: q || undefined,
              category_id: categoryId || undefined,
              include_inactive: includeInactive,
              cursor: pageParam ?? undefined,
            },
          },
        }),
      ),
    getNextPageParam: (page) => page.next_cursor,
  });
  const items = products.data?.pages.flatMap((page) => page.items) ?? [];
  const filtered = Boolean(q || categoryId);

  return (
    <>
      <PageHeader
        title="Catálogo"
        description="Productos y servicios, quién te los ofrece y a qué costo."
        actions={
          can("catalog.edit") ? (
            <Link href="/catalog/new" className={buttonClasses()}>
              <Plus className="size-4" aria-hidden /> Nuevo producto
            </Link>
          ) : null
        }
      />
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center">
        <SearchBox value={search} onChange={setSearch} label="Buscar producto" />
        <select
          aria-label="Rubro"
          value={categoryId}
          onChange={(e) => setCategoryId(e.target.value)}
          className="h-11 rounded-lg border border-line bg-surface px-3 text-base sm:h-10 sm:w-56 sm:text-sm"
        >
          <option value="">Todos los rubros</option>
          {categoryOptions(categories.data ?? []).map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <CheckboxField
          label="Ver inactivos"
          checked={includeInactive}
          onChange={(e) => setIncludeInactive(e.target.checked)}
        />
      </div>
      {products.isError ? <Notice tone="error">{errorMessage(products.error)}</Notice> : null}
      {products.isPending ? <p className="text-sm text-ink-muted">Cargando…</p> : null}
      {products.isSuccess && items.length === 0 ? (
        <EmptyState title={filtered ? "No hay productos que coincidan" : "Tu catálogo está vacío"}>
          {filtered
            ? "Probá con otra búsqueda o rubro."
            : "Cargá lo que presupuestás seguido: estructuras, gráfica, técnica, personal…"}
        </EmptyState>
      ) : null}
      {items.length > 0 ? (
        <ul className="divide-y divide-line rounded-xl border border-line bg-surface">
          {items.map((product) => (
            <li key={product.id}>
              <Link href={`/catalog/${product.id}`} className="flex items-center gap-3 px-4 py-3 hover:bg-subtle">
                <div className="min-w-0 flex-1">
                  <p className="flex items-center gap-2 truncate font-medium">
                    {product.name}
                    {!product.is_active ? (
                      <span className="rounded bg-subtle px-1.5 text-xs font-normal text-ink-muted">Inactivo</span>
                    ) : null}
                  </p>
                  <p className="truncate text-sm text-ink-muted">
                    {product.category_name} · por {product.unit_code}
                    {product.charge_mode === "PER_DAY" ? ` · ${CHARGE_MODE_LABELS.PER_DAY.toLowerCase()}` : ""}
                    {" · "}
                    {product.preferred ? product.preferred.supplier_name : "Sin proveedor"}
                    {product.offers_count > 1 ? ` (+${product.offers_count - 1})` : ""}
                  </p>
                  {showCost && product.preferred ? (
                    <div className="mt-1 sm:hidden">
                      <CostLabel cost={product.preferred.current_cost} compact />
                    </div>
                  ) : null}
                </div>
                {showCost && product.preferred ? (
                  <div className="hidden text-right sm:block">
                    <CostLabel cost={product.preferred.current_cost} compact />
                  </div>
                ) : null}
                <ChevronRight className="size-4 text-ink-muted" aria-hidden />
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
      {products.hasNextPage ? (
        <div className="mt-4 flex justify-center">
          <Button variant="secondary" loading={products.isFetchingNextPage} onClick={() => void products.fetchNextPage()}>
            Ver más
          </Button>
        </div>
      ) : null}
    </>
  );
}
