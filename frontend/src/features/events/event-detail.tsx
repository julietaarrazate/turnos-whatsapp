"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ChevronRight, Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Button, buttonClasses } from "@/components/ui/button";
import { TextField } from "@/components/ui/field";
import { Notice } from "@/components/ui/notice";
import { useSession } from "@/features/auth/session";
import { BUDGETS_KEY, EVENTS_KEY } from "@/features/budgets/keys";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import type { EventDetail, EventStatus, Schemas } from "@/lib/api/types";
import { formatDate, formatDateTime } from "@/lib/format/date";
import { formatMoney } from "@/lib/format/number";
import { textValue } from "@/lib/form";

import { EVENT_STATUS_LABELS, EventStatusBadge } from "./status";

const eventKey = (id: string) => [...EVENTS_KEY, "detail", id] as const;

function StatusActions({ event }: { event: EventDetail }) {
  const queryClient = useQueryClient();
  const [target, setTarget] = useState<EventStatus | null>(null);
  const change = useMutation({
    mutationFn: async (body: Schemas["StatusChangeIn"]) =>
      unwrap(await api.POST("/api/v1/events/{event_id}/status", { params: { path: { event_id: event.id } }, body })),
    onSuccess: (data) => {
      queryClient.setQueryData(eventKey(event.id), data);
      void queryClient.invalidateQueries({ queryKey: EVENTS_KEY });
      setTarget(null);
    },
  });
  const options: EventStatus[] = [];
  if (["LEAD", "QUOTING", "SENT", "NEGOTIATION"].includes(event.status)) options.push("LOST");
  if (["LEAD", "QUOTING", "APPROVED", "IN_PRODUCTION"].includes(event.status)) options.push("CANCELLED");
  if (event.status === "LOST") options.push("QUOTING");
  if (!options.length) return null;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-2">
        {options.map((status) => (
          <Button
            key={status}
            variant={status === "QUOTING" ? "secondary" : "ghost"}
            size="sm"
            onClick={() => (status === "QUOTING" ? change.mutate({ to_status: status }) : setTarget(status))}
          >
            {status === "LOST" ? "Marcar perdido" : status === "CANCELLED" ? "Cancelar evento" : "Reabrir"}
          </Button>
        ))}
      </div>
      {target ? (
        <form
          aria-label={`Motivo: ${EVENT_STATUS_LABELS[target]}`}
          className="flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            change.mutate({ to_status: target, reason: textValue(new FormData(e.currentTarget), "reason") });
          }}
        >
          <div className="min-w-60 flex-1">
            <TextField
              label={target === "LOST" ? "¿Por qué se perdió?" : "¿Por qué se cancela?"}
              name="reason"
              required
              autoFocus
              maxLength={2000}
              placeholder={target === "LOST" ? "Ej.: eligió otra productora por precio" : "Ej.: se suspendió el evento"}
            />
          </div>
          <Button type="submit" size="sm" variant="danger" loading={change.isPending}>
            Confirmar
          </Button>
          <Button type="button" size="sm" variant="ghost" onClick={() => setTarget(null)}>
            Volver
          </Button>
        </form>
      ) : null}
      {change.isError ? <Notice tone="error">{errorMessage(change.error)}</Notice> : null}
    </div>
  );
}

export function EventDetailPage({ id }: { id: string }) {
  const { can } = useSession();
  const event = useQuery({
    queryKey: eventKey(id),
    queryFn: async () => unwrap(await api.GET("/api/v1/events/{event_id}", { params: { path: { event_id: id } } })),
  });
  const budgets = useQuery({
    queryKey: [...BUDGETS_KEY, "list", "event", id],
    queryFn: async () => unwrap(await api.GET("/api/v1/budgets", { params: { query: { event_id: id } } })),
  });

  if (event.isPending) return <p className="text-sm text-ink-muted">Cargando…</p>;
  if (event.isError) return <Notice tone="error">{errorMessage(event.error)}</Notice>;
  const data = event.data;
  const quotable = !["LOST", "CANCELLED", "CLOSED", "COMPLETED"].includes(data.status);

  return (
    <>
      <Link href="/events" className="mb-3 inline-flex items-center gap-1 text-sm text-ink-muted hover:text-ink">
        <ArrowLeft className="size-4" aria-hidden /> Eventos
      </Link>
      <header className="mb-4">
        <h1 className="flex flex-wrap items-center gap-2 text-xl font-semibold tracking-tight sm:text-2xl">
          #{data.number} · {data.name} <EventStatusBadge status={data.status} />
        </h1>
        <p className="mt-1 text-sm text-ink-muted">
          <Link href={`/clients/${data.client_id}`} className="hover:underline">
            {data.client_name}
          </Link>
          {" · "}
          {data.start_date ? formatDate(data.start_date) : "fecha a confirmar"}
          {data.event_days > 1 ? ` · ${data.event_days} días` : ""}
          {data.venue ? ` · ${data.venue}` : ""}
          {data.city ? ` · ${data.city}` : ""}
        </p>
        {data.lost_reason ? <p className="mt-1 text-sm text-danger">Perdido: {data.lost_reason}</p> : null}
        {data.cancel_reason ? <p className="mt-1 text-sm text-danger">Cancelado: {data.cancel_reason}</p> : null}
      </header>

      <section className="mb-4 rounded-xl border border-line bg-surface">
        <div className="flex items-center justify-between border-b border-line px-5 py-3">
          <h2 className="font-semibold">Presupuestos</h2>
          {can("budget.edit") && quotable ? (
            <Link href={`/budgets/new?event=${data.id}`} className={buttonClasses("secondary", "sm")}>
              <Plus className="size-4" aria-hidden /> Otro presupuesto
            </Link>
          ) : null}
        </div>
        <ul className="divide-y divide-line">
          {budgets.data?.items.map((budget) => (
            <li key={budget.id}>
              <Link href={`/budgets/${budget.id}`} className="flex items-center gap-3 px-5 py-3 hover:bg-subtle">
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium">
                    #{budget.number} · {budget.title}
                  </span>
                  <span className="block text-sm text-ink-muted">
                    v{budget.version_no}
                    {budget.version_status === "DRAFT" ? " (borrador)" : ""}
                    {budget.approved_version_no ? (
                      <span className="ml-2 rounded bg-success/10 px-1.5 py-0.5 text-xs text-success">Aprobado v{budget.approved_version_no}</span>
                    ) : null}
                  </span>
                </span>
                <span className="font-medium tabular-nums">{formatMoney(budget.sale_net)}</span>
                <ChevronRight className="size-4 text-ink-muted" aria-hidden />
              </Link>
            </li>
          ))}
        </ul>
        {budgets.data?.items.length === 0 ? <p className="px-5 py-3 text-sm text-ink-muted">Todavía no tiene presupuestos.</p> : null}
      </section>

      {can("proposal.decide") ? (
        <section className="mb-4 rounded-xl border border-line bg-surface p-5">
          <h2 className="mb-3 font-semibold">Estado</h2>
          <StatusActions event={data} />
        </section>
      ) : null}

      <section className="rounded-xl border border-line bg-surface p-5">
        <h2 className="mb-3 font-semibold">Historial</h2>
        <ol className="flex flex-col gap-2 text-sm">
          {data.history.map((h, i) => (
            <li key={i} className="flex flex-wrap gap-x-2">
              <span className="text-ink-muted">{formatDateTime(h.at)}</span>
              <span>{EVENT_STATUS_LABELS[h.to_status]}</span>
              {h.changed_by_name ? <span className="text-ink-muted">· {h.changed_by_name}</span> : null}
              {h.reason ? <span className="text-ink-muted">· {h.reason}</span> : null}
            </li>
          ))}
        </ol>
      </section>
    </>
  );
}
