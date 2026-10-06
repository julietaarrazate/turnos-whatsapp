"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronRight, Plus } from "lucide-react";
import Link from "next/link";
import { useDeferredValue, useState } from "react";

import { buttonClasses } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Notice } from "@/components/ui/notice";
import { PageHeader } from "@/components/ui/page-header";
import { SearchBox } from "@/components/ui/search-box";
import { useSession } from "@/features/auth/session";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import type { Schemas } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatDateTime, formatDay } from "@/lib/format/date";
import { formatMoney } from "@/lib/format/number";

import { BUDGETS_KEY } from "./keys";

type PipelineStatus = Schemas["PipelineStatus"];
type PipelineItem = Schemas["PipelineItem"];
type FollowUp = Schemas["FollowUp"];

export const PIPELINE_KEY = [...BUDGETS_KEY, "pipeline"] as const;

const STATUS: Record<PipelineStatus, { label: string; tone: string }> = {
  DRAFT: { label: "Borrador", tone: "bg-subtle text-ink-muted" },
  SENT: { label: "Enviado", tone: "bg-accent/10 text-accent" },
  VIEWED: { label: "Visto", tone: "bg-accent/10 text-accent" },
  NEGOTIATION: { label: "Negociación", tone: "bg-warning/15 text-warning" },
  ACCEPTED: { label: "Aceptado", tone: "bg-success/10 text-success" },
  LOST: { label: "Perdido", tone: "bg-danger/10 text-danger" },
};
const ORDER: PipelineStatus[] = ["DRAFT", "SENT", "VIEWED", "NEGOTIATION", "ACCEPTED", "LOST"];

export function followUpText(item: PipelineItem, days: number): string | null {
  const last = item.last_proposal;
  if (!item.follow_up || !last) return null;
  const reasons: Record<FollowUp, string> = {
    EXPIRING: `vence el ${formatDay(last.valid_until)}`,
    VIEWED_NO_ANSWER: `la vio el ${last.first_viewed_at ? formatDateTime(last.first_viewed_at) : ""} y no respondió`,
    NO_RESPONSE: `enviada hace más de ${days} días, sin respuesta`,
  };
  return `Para seguir: ${reasons[item.follow_up]}`;
}

type Filter = PipelineStatus | "FOLLOW_UP" | null;

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        "h-8 shrink-0 rounded-full border px-3 text-sm",
        active ? "border-accent bg-accent text-white" : "border-line bg-surface text-ink hover:bg-subtle",
      )}
    >
      {children}
    </button>
  );
}

/** B-12: pipeline comercial con estado derivado y "para seguir". */
export function BudgetsList() {
  const { can } = useSession();
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<Filter>(null);
  const q = useDeferredValue(search.trim());
  const pipeline = useQuery({
    queryKey: [...PIPELINE_KEY, q],
    queryFn: async () => unwrap(await api.GET("/api/v1/pipeline", { params: { query: { q: q || undefined } } })),
  });
  const data = pipeline.data;
  const items = (data?.items ?? []).filter((item) =>
    filter === null ? true : filter === "FOLLOW_UP" ? item.follow_up !== null : item.pipeline_status === filter,
  );

  return (
    <>
      <PageHeader
        title="Presupuestos"
        description="El pipeline comercial: en qué está cada presupuesto y a quién hay que seguir."
        actions={
          can("budget.edit") ? (
            <Link href="/budgets/new" className={buttonClasses()}>
              <Plus className="size-4" aria-hidden /> Nuevo presupuesto
            </Link>
          ) : null
        }
      />
      <div className="mb-3 flex">
        <SearchBox value={search} onChange={setSearch} label="Buscar por evento, cliente o título" />
      </div>
      {data ? (
        <div role="group" aria-label="Filtrar por estado" className="-mx-4 mb-4 flex gap-2 overflow-x-auto px-4 pb-1">
          <Chip active={filter === null} onClick={() => setFilter(null)}>
            Todos
          </Chip>
          <Chip active={filter === "FOLLOW_UP"} onClick={() => setFilter("FOLLOW_UP")}>
            Para seguir · {data.follow_up}
          </Chip>
          {ORDER.map((status) => (
            <Chip key={status} active={filter === status} onClick={() => setFilter(status)}>
              {STATUS[status].label} · {data.counts[status] ?? 0}
            </Chip>
          ))}
        </div>
      ) : null}
      {pipeline.isError ? <Notice tone="error">{errorMessage(pipeline.error)}</Notice> : null}
      {pipeline.isPending ? <p className="text-sm text-ink-muted">Cargando…</p> : null}
      {data?.truncated ? (
        <Notice tone="info">Se muestran los {data.items.length} presupuestos más recientes. Buscá para encontrar uno más viejo.</Notice>
      ) : null}
      {pipeline.isSuccess && items.length === 0 ? (
        <EmptyState title={q || filter ? "No hay presupuestos que coincidan" : "Todavía no hiciste presupuestos"}>
          {q || filter ? "Probá con otra búsqueda o filtro." : "Empezá por uno: cliente, evento y listo."}
        </EmptyState>
      ) : null}
      {items.length > 0 && data ? (
        <ul aria-label="Presupuestos" className="divide-y divide-line rounded-xl border border-line bg-surface">
          {items.map((item) => {
            const followUp = followUpText(item, data.follow_up_days);
            return (
              <li key={item.id}>
                <Link href={`/budgets/${item.id}`} className="flex items-center gap-3 px-4 py-3 hover:bg-subtle">
                  <div className="min-w-0 flex-1">
                    <p className="flex flex-wrap items-center gap-2">
                      <span className="truncate font-medium">
                        #{item.number} · {item.title}
                      </span>
                      <span className={cn("rounded px-1.5 py-0.5 text-xs", STATUS[item.pipeline_status].tone)}>
                        {STATUS[item.pipeline_status].label}
                      </span>
                    </p>
                    <p className="truncate text-sm text-ink-muted">
                      {item.client_name} · v{item.version_no}
                      {item.version_status === "DRAFT" ? " (borrador)" : ""} · {formatDateTime(item.updated_at)}
                    </p>
                    {followUp ? <p className="text-sm font-medium text-warning">{followUp}</p> : null}
                  </div>
                  <span className="text-right font-medium tabular-nums">{formatMoney(item.sale_net)}</span>
                  <ChevronRight className="size-4 text-ink-muted" aria-hidden />
                </Link>
              </li>
            );
          })}
        </ul>
      ) : null}
    </>
  );
}
