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
import { EventStatusBadge } from "@/features/events/status";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import { formatDateTime } from "@/lib/format/date";
import { formatMoney } from "@/lib/format/number";

import { BUDGETS_KEY } from "./keys";

export function BudgetsList() {
  const { can } = useSession();
  const [search, setSearch] = useState("");
  const q = useDeferredValue(search.trim());
  const budgets = useInfiniteQuery({
    queryKey: [...BUDGETS_KEY, "list", q],
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam }) =>
      unwrap(await api.GET("/api/v1/budgets", { params: { query: { q: q || undefined, cursor: pageParam ?? undefined } } })),
    getNextPageParam: (page) => page.next_cursor,
  });
  const items = budgets.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <>
      <PageHeader
        title="Presupuestos"
        description="Del más reciente al más viejo."
        actions={
          can("budget.edit") ? (
            <Link href="/budgets/new" className={buttonClasses()}>
              <Plus className="size-4" aria-hidden /> Nuevo presupuesto
            </Link>
          ) : null
        }
      />
      <div className="mb-4 flex">
        <SearchBox value={search} onChange={setSearch} label="Buscar por evento, cliente o título" />
      </div>
      {budgets.isError ? <Notice tone="error">{errorMessage(budgets.error)}</Notice> : null}
      {budgets.isPending ? <p className="text-sm text-ink-muted">Cargando…</p> : null}
      {budgets.isSuccess && items.length === 0 ? (
        <EmptyState title={q ? "No hay presupuestos que coincidan" : "Todavía no hiciste presupuestos"}>
          {q ? "Probá con otra búsqueda." : "Empezá por uno: cliente, evento y listo."}
        </EmptyState>
      ) : null}
      {items.length > 0 ? (
        <ul className="divide-y divide-line rounded-xl border border-line bg-surface">
          {items.map((budget) => (
            <li key={budget.id}>
              <Link href={`/budgets/${budget.id}`} className="flex items-center gap-3 px-4 py-3 hover:bg-subtle">
                <div className="min-w-0 flex-1">
                  <p className="flex flex-wrap items-center gap-2">
                    <span className="truncate font-medium">
                      #{budget.number} · {budget.title}
                    </span>
                    <EventStatusBadge status={budget.event_status} />
                  </p>
                  <p className="truncate text-sm text-ink-muted">
                    {budget.client_name} · v{budget.version_no}
                    {budget.version_status === "DRAFT" ? " (borrador)" : ""} · {formatDateTime(budget.updated_at)}
                  </p>
                </div>
                <span className="text-right font-medium tabular-nums">{formatMoney(budget.sale_net)}</span>
                <ChevronRight className="size-4 text-ink-muted" aria-hidden />
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
      {budgets.hasNextPage ? (
        <div className="mt-4 flex justify-center">
          <Button variant="secondary" loading={budgets.isFetchingNextPage} onClick={() => void budgets.fetchNextPage()}>
            Ver más
          </Button>
        </div>
      ) : null}
    </>
  );
}
