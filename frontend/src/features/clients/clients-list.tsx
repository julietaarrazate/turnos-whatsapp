"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import { ChevronRight, Plus } from "lucide-react";
import Link from "next/link";
import { useDeferredValue, useState } from "react";

import { Button, buttonClasses } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Notice } from "@/components/ui/notice";
import { PageHeader } from "@/components/ui/page-header";
import { SearchBox } from "@/components/ui/search-box";
import { useSession } from "@/features/auth/session";
import { api, errorMessage, unwrap } from "@/lib/api/client";

export const CLIENTS_KEY = ["clients"] as const;

export function ClientsList() {
  const { can } = useSession();
  const [search, setSearch] = useState("");
  const q = useDeferredValue(search.trim());
  const clients = useInfiniteQuery({
    queryKey: [...CLIENTS_KEY, "list", q],
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam }) =>
      unwrap(
        await api.GET("/api/v1/clients", {
          params: { query: { q: q || undefined, cursor: pageParam ?? undefined } },
        }),
      ),
    getNextPageParam: (page) => page.next_cursor,
  });
  const items = clients.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <>
      <PageHeader
        title="Clientes"
        description="Empresas y contactos a los que les presupuestás."
        actions={
          can("clients.edit") ? (
            <Link href="/clients/new" className={buttonClasses()}>
              <Plus className="size-4" aria-hidden /> Nuevo cliente
            </Link>
          ) : null
        }
      />
      <div className="mb-4 flex">
        <SearchBox value={search} onChange={setSearch} label="Buscar por nombre o CUIT" />
      </div>
      {clients.isError ? <Notice tone="error">{errorMessage(clients.error)}</Notice> : null}
      {clients.isPending ? <p className="text-sm text-ink-muted">Cargando…</p> : null}
      {clients.isSuccess && items.length === 0 ? (
        <EmptyState title={q ? "No hay clientes que coincidan" : "Todavía no cargaste clientes"}>
          {q ? "Probá con otra búsqueda." : "Agregá el primero para poder presupuestarle."}
        </EmptyState>
      ) : null}
      {items.length > 0 ? (
        <ul className="divide-y divide-line rounded-xl border border-line bg-surface">
          {items.map((client) => (
            <li key={client.id}>
              <Link href={`/clients/${client.id}`} className="flex items-center gap-3 px-4 py-3 hover:bg-subtle">
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">{client.name}</p>
                  <p className="truncate text-sm text-ink-muted">
                    {[client.primary_contact, client.city, client.tax_id].filter(Boolean).join(" · ") || "Sin datos de contacto"}
                  </p>
                </div>
                <ChevronRight className="size-4 text-ink-muted" aria-hidden />
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
      {clients.hasNextPage ? (
        <div className="mt-4 flex justify-center">
          <Button variant="secondary" loading={clients.isFetchingNextPage} onClick={() => void clients.fetchNextPage()}>
            Ver más
          </Button>
        </div>
      ) : null}
    </>
  );
}
