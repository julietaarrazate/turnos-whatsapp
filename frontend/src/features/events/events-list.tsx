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
import { EVENTS_KEY } from "@/features/budgets/keys";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import type { EventStatus } from "@/lib/api/types";
import { formatDate } from "@/lib/format/date";

import { EVENT_STATUS_LABELS, EventStatusBadge } from "./status";

const FILTERS: { label: string; statuses: EventStatus[] }[] = [
  { label: "Activos", statuses: ["LEAD", "QUOTING", "SENT", "NEGOTIATION", "APPROVED", "IN_PRODUCTION"] },
  { label: "Todos", statuses: [] },
  { label: EVENT_STATUS_LABELS.LOST, statuses: ["LOST"] },
];

export function EventsList() {
  const { can } = useSession();
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState(0);
  const q = useDeferredValue(search.trim());
  const statuses = FILTERS[filter].statuses;
  const events = useInfiniteQuery({
    queryKey: [...EVENTS_KEY, "list", q, filter],
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam }) =>
      unwrap(
        await api.GET("/api/v1/events", {
          params: {
            query: { q: q || undefined, status: statuses.length ? statuses : undefined, cursor: pageParam ?? undefined },
          },
        }),
      ),
    getNextPageParam: (page) => page.next_cursor,
  });
  const items = events.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <>
      <PageHeader
        title="Eventos"
        description="Cada evento con sus presupuestos y su estado."
        actions={
          can("budget.edit") ? (
            <Link href="/budgets/new" className={buttonClasses()}>
              <Plus className="size-4" aria-hidden /> Nuevo presupuesto
            </Link>
          ) : null
        }
      />
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center">
        <SearchBox value={search} onChange={setSearch} label="Buscar por evento o cliente" />
        <div role="group" aria-label="Filtro" className="flex gap-1">
          {FILTERS.map((f, i) => (
            <button
              key={f.label}
              type="button"
              aria-pressed={filter === i}
              onClick={() => setFilter(i)}
              className={`rounded-full border px-3 py-1.5 text-sm ${filter === i ? "border-accent bg-accent/10 text-accent" : "border-line text-ink-muted"}`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>
      {events.isError ? <Notice tone="error">{errorMessage(events.error)}</Notice> : null}
      {events.isPending ? <p className="text-sm text-ink-muted">Cargando…</p> : null}
      {events.isSuccess && items.length === 0 ? (
        <EmptyState title="No hay eventos">Se crean al hacer un presupuesto nuevo.</EmptyState>
      ) : null}
      {items.length ? (
        <ul className="divide-y divide-line rounded-xl border border-line bg-surface">
          {items.map((event) => (
            <li key={event.id}>
              <Link href={`/events/${event.id}`} className="flex items-center gap-3 px-4 py-3 hover:bg-subtle">
                <div className="min-w-0 flex-1">
                  <p className="flex flex-wrap items-center gap-2">
                    <span className="truncate font-medium">
                      #{event.number} · {event.name}
                    </span>
                    <EventStatusBadge status={event.status} />
                  </p>
                  <p className="truncate text-sm text-ink-muted">
                    {event.client_name} · {event.start_date ? formatDate(event.start_date) : "fecha a confirmar"}
                    {event.city ? ` · ${event.city}` : ""}
                    {event.responsible_name ? ` · ${event.responsible_name}` : ""}
                  </p>
                </div>
                <ChevronRight className="size-4 text-ink-muted" aria-hidden />
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
      {events.hasNextPage ? (
        <div className="mt-4 flex justify-center">
          <Button variant="secondary" loading={events.isFetchingNextPage} onClick={() => void events.fetchNextPage()}>
            Ver más
          </Button>
        </div>
      ) : null}
    </>
  );
}
