"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Notice } from "@/components/ui/notice";
import { EventStatusBadge } from "@/features/events/status";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import type { Schemas } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatDay } from "@/lib/format/date";
import { formatMoney, formatPercentCompact } from "@/lib/format/number";

type Dashboard = Schemas["DashboardOut"];

function thisMonth(): string {
  return new Intl.DateTimeFormat("en-CA", { year: "numeric", month: "2-digit", timeZone: "America/Argentina/Buenos_Aires" })
    .format(new Date())
    .slice(0, 7);
}

function Kpi({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="min-w-0 rounded-xl border border-line bg-surface p-4">
      <p className="text-xs uppercase tracking-wide text-ink-muted">{label}</p>
      <p className="mt-1 truncate text-xl font-semibold tabular-nums sm:text-2xl">{value}</p>
      {detail ? <p className="mt-0.5 text-xs text-ink-muted">{detail}</p> : null}
    </div>
  );
}

function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}

type Pending = Dashboard["todo"]["operations"][number];

/** Lo operativo, por evento: lleva a la pestaña Producción, donde se resuelve (y está el WhatsApp). */
function pendingText(p: Pending): string {
  const event = `#${p.event_number} ${p.event_name}`;
  switch (p.kind) {
    case "TASKS_OVERDUE":
      return `${plural(p.count, "tarea atrasada", "tareas atrasadas")} · ${event}`;
    case "TASKS_TODAY":
      return `${plural(p.count, "tarea", "tareas")} para hoy · ${event}`;
    case "TO_CONFIRM":
      return `${plural(p.count, "proveedor sin confirmar", "proveedores sin confirmar")} · ${event}${p.date ? ` (${formatDay(p.date)})` : ""}`;
    case "TO_PAY":
      return `${plural(p.count, "factura por pagar", "facturas por pagar")} · ${event}`;
  }
}

function Todo({ data }: { data: Dashboard["todo"] }) {
  const items = [
    ...data.operations.map((p) => ({
      count: p.count,
      text: pendingText(p),
      href: `/events/${p.event_id}/production`,
      urgent: p.kind === "TASKS_OVERDUE",
    })),
    { count: data.no_response, text: `${plural(data.no_response, "propuesta", "propuestas")} sin respuesta hace +${data.follow_up_days} días`, href: "/budgets" },
    { count: data.viewed_no_answer, text: `${plural(data.viewed_no_answer, "propuesta vista", "propuestas vistas")} y no respondida${data.viewed_no_answer === 1 ? "" : "s"}`, href: "/budgets" },
    { count: data.expiring, text: `${plural(data.expiring, "propuesta vence", "propuestas vencen")} en menos de 48 h`, href: "/budgets" },
    { count: data.stale_costs, text: `${plural(data.stale_costs, "costo desactualizado", "costos desactualizados")} en presupuestos abiertos`, href: "/budgets" },
  ].filter((item) => item.count > 0);
  return (
    <section aria-label="Para hacer hoy" className="rounded-xl border border-line bg-surface">
      <h2 className="border-b border-line px-4 py-3 font-semibold">Para hacer hoy</h2>
      {items.length ? (
        <ul className="divide-y divide-line">
          {items.map((item) => (
            <li key={item.text}>
              <Link href={item.href} className="flex items-center gap-3 px-4 py-3 text-sm hover:bg-subtle">
                <span className={`size-2 shrink-0 rounded-full ${"urgent" in item && item.urgent ? "bg-danger" : "bg-warning"}`} aria-hidden />
                <span className="min-w-0 flex-1">{item.text}</span>
                <ChevronRight className="size-4 text-ink-muted" aria-hidden />
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <p className="px-4 py-3 text-sm text-ink-muted">Nada pendiente para hoy.</p>
      )}
    </section>
  );
}

function Upcoming({ events }: { events: Dashboard["upcoming"] }) {
  return (
    <section aria-label="Próximos eventos" className="rounded-xl border border-line bg-surface">
      <div className="flex items-center justify-between border-b border-line px-4 py-3">
        <h2 className="font-semibold">Próximos eventos</h2>
        <Link href="/events" className="text-sm text-accent hover:underline">
          Ver eventos
        </Link>
      </div>
      {events.length ? (
        <ul className="divide-y divide-line">
          {events.map((event) => (
            <li key={event.id}>
              <Link href={`/events/${event.id}`} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3 text-sm hover:bg-subtle">
                <span className="w-20 shrink-0 text-ink-muted">{formatDay(event.start_date)}</span>
                <span className="min-w-0 flex-1 truncate">
                  <span className="font-medium">{event.client_name}</span> · {event.name}
                </span>
                <EventStatusBadge status={event.status} />
                {event.margin !== null ? <span className="tabular-nums text-ink-muted">margen {formatPercentCompact(event.margin)}</span> : null}
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <p className="px-4 py-3 text-sm text-ink-muted">No hay eventos aprobados con fecha próxima.</p>
      )}
    </section>
  );
}

type Active = Dashboard["active"][number];

function todayLabel(): string {
  const text = new Intl.DateTimeFormat("es-AR", {
    weekday: "long",
    day: "numeric",
    month: "long",
    timeZone: "America/Argentina/Buenos_Aires",
  }).format(new Date());
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** El pulso: saludo y los tres números que importan al abrir la app. */
function Pulse({ greeting, active }: { greeting: string; active: Active[] | undefined }) {
  const late = active?.reduce((sum, e) => sum + e.late, 0);
  const ready = active?.reduce((sum, e) => sum + e.pieces_ready, 0);
  const total = active?.reduce((sum, e) => sum + e.pieces_total, 0);
  return (
    <section aria-label="Pulso" className="flex flex-col gap-4 rounded-2xl bg-brand p-5 text-white">
      <div>
        <p className="text-sm text-white/85">{todayLabel()}</p>
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{greeting}</h1>
      </div>
      <div className="grid grid-cols-3 gap-2">
        <div className="rounded-xl bg-white/12 px-3 py-2.5">
          <p className="text-2xl font-extrabold tabular-nums">{active ? active.length : "—"}</p>
          <p className="text-xs text-white/90">eventos activos</p>
        </div>
        <div className={cn("rounded-xl px-3 py-2.5", late ? "bg-white text-danger" : "bg-white/12")}>
          <p className="text-2xl font-extrabold tabular-nums">{late ?? "—"}</p>
          <p className={cn("text-xs", late ? "font-semibold" : "text-white/90")}>{late === 1 ? "atraso" : "atrasos"}</p>
        </div>
        <div className="rounded-xl bg-white/12 px-3 py-2.5">
          <p className="text-2xl font-extrabold tabular-nums">{total ? `${ready}/${total}` : "—"}</p>
          <p className="text-xs text-white/90">piezas listas</p>
        </div>
      </div>
    </section>
  );
}

function ActiveEvents({ events }: { events: Active[] }) {
  return (
    <section aria-label="Eventos activos" className="flex flex-col gap-3">
      <div className="flex items-baseline justify-between">
        <h2 className="text-lg font-bold tracking-tight">Eventos activos</h2>
        <Link href="/events" className="text-sm font-semibold text-accent hover:underline">
          Ver todos
        </Link>
      </div>
      {events.length === 0 ? (
        <p className="rounded-xl border border-line bg-surface px-4 py-3 text-sm text-ink-muted">
          No hay eventos aprobados ni en producción.
        </p>
      ) : (
        <ul className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {events.map((event) => (
            <li key={event.id}>
              <Link
                href={`/events/${event.id}/pieces`}
                className={cn(
                  "flex flex-col gap-2.5 rounded-2xl border bg-surface p-4 shadow-sm hover:bg-subtle",
                  event.late ? "border-danger/40" : "border-line",
                )}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate text-xs font-semibold tracking-wide text-ink-muted uppercase">
                      #{event.number} · {event.client_name}
                    </p>
                    <p className="truncate text-base font-bold tracking-tight">{event.name}</p>
                  </div>
                  {event.late ? (
                    <span className="shrink-0 rounded-full bg-danger/10 px-2.5 py-1 text-xs font-bold text-danger">
                      {plural(event.late, "atraso", "atrasos")}
                    </span>
                  ) : null}
                </div>
                <div className="h-2 overflow-hidden rounded bg-subtle">
                  <div className="h-2 rounded bg-brand" style={{ width: `${event.progress}%` }} />
                </div>
                <div className="flex justify-between gap-2 text-sm text-ink-muted">
                  <span>
                    {event.pieces_total ? (
                      <>
                        <strong className="text-ink">{event.progress}%</strong> · {event.pieces_ready} de {event.pieces_total} piezas
                      </>
                    ) : (
                      "Sin piezas cargadas"
                    )}
                  </span>
                  <span>{event.mount_date ? `Montaje ${formatDay(event.mount_date)}` : "Fecha a confirmar"}</span>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** A-01: qué está pasando con el negocio, en 5 segundos (PRODUCT_SPEC §4.1). */
export function DashboardView({ greeting }: { greeting: string }) {
  const [month, setMonth] = useState(thisMonth);
  const query = useQuery({
    queryKey: ["dashboard", month],
    queryFn: async () => unwrap(await api.GET("/api/v1/dashboard", { params: { query: { month } } })),
  });
  return (
    <div className="flex flex-col gap-5">
      <Pulse greeting={greeting} active={query.data?.active} />
      {query.isError ? <Notice tone="error">{errorMessage(query.error)}</Notice> : null}
      {query.data ? (
        <>
          <ActiveEvents events={query.data.active} />
          <Todo data={query.data.todo} />
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-lg font-bold tracking-tight">Comercial</h2>
            <label className="flex items-center gap-2 text-sm">
              <span className="text-ink-muted">Mes</span>
              <input
                type="month"
                aria-label="Mes del tablero"
                value={month}
                onChange={(e) => e.target.value && setMonth(e.target.value)}
                className="h-9 rounded-lg border border-line bg-surface px-2"
              />
            </label>
            {query.data.own_only ? <span className="w-full text-xs text-ink-muted">Tus presupuestos</span> : null}
          </div>
          <section aria-label="Indicadores" className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Kpi label="Enviado" value={formatMoney(query.data.sent.amount)} detail={plural(query.data.sent.count, "presupuesto", "presupuestos")} />
            <Kpi label="Aceptado" value={formatMoney(query.data.accepted.amount)} detail={plural(query.data.accepted.count, "presupuesto", "presupuestos")} />
            <Kpi label="En negociación" value={formatMoney(query.data.in_negotiation.amount)} detail="hoy" />
            <Kpi
              label="Margen prom. aceptado"
              value={query.data.avg_margin ? formatPercentCompact(query.data.avg_margin) : "—"}
              detail={
                query.data.conversion.by_count !== null ? `Conversión 90 días: ${formatPercentCompact(query.data.conversion.by_count)}` : "Sin decisiones en 90 días"
              }
            />
          </section>
          <Upcoming events={query.data.upcoming} />
        </>
      ) : query.isPending ? (
        <p className="text-sm text-ink-muted">Cargando…</p>
      ) : null}
    </div>
  );
}
