"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { HandieMark } from "@/components/brand/handie-logo";
import { Button } from "@/components/ui/button";
import { Notice } from "@/components/ui/notice";
import { ROLE_LABELS } from "@/features/auth/roles";
import { useMeQuery } from "@/features/auth/session";
import { ACTION_LABELS } from "@/features/settings/audit-log";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import type { PlatformOrg, PlatformOverview, PlatformSession, PlatformUser, Role } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatDateTime } from "@/lib/format/date";

import { describeDevice, timeAgo } from "./device";

const OVERVIEW_KEY = ["platform", "overview"] as const;
const RECENT_MS = 60 * 60_000;

type Tab = "summary" | "organizations" | "people" | "sessions" | "activity";
const TABS: { id: Tab; label: string }[] = [
  { id: "summary", label: "Resumen" },
  { id: "organizations", label: "Organizaciones" },
  { id: "people", label: "Personas" },
  { id: "sessions", label: "Sesiones abiertas" },
  { id: "activity", label: "Actividad" },
];

function roleLabel(role: string): string {
  return ROLE_LABELS[role as Role] ?? role;
}

/** Para cualquiera que no sea la dueña de la plataforma, esta página "no existe". */
function NotFound() {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-3 p-6 text-center">
      <p className="text-5xl font-extrabold text-ink-muted">404</p>
      <p className="text-ink-muted">Esta página no existe.</p>
      <Link href="/" className="text-sm font-semibold text-brand underline">
        Ir al inicio
      </Link>
    </main>
  );
}

export function PlatformPanel() {
  const me = useMeQuery();
  if (me.isPending) {
    return (
      <div className="flex min-h-dvh items-center justify-center" aria-busy>
        <span className="size-6 animate-spin rounded-full border-2 border-accent border-t-transparent" />
      </div>
    );
  }
  if (me.isError || !me.data.platform_admin) return <NotFound />;
  return <Panel />;
}

function Panel() {
  const [tab, setTab] = useState<Tab>("summary");
  const overview = useQuery({
    queryKey: OVERVIEW_KEY,
    queryFn: async () => unwrap(await api.GET("/api/v1/admin/overview")),
    refetchInterval: 60_000,
  });

  return (
    <div className="min-h-dvh bg-canvas">
      <header className="sticky top-0 z-10 flex h-14 items-center gap-3 bg-bar px-4 text-white">
        <HandieMark className="size-8" />
        <h1 className="flex flex-1 items-center gap-2 text-lg font-bold">
          <ShieldCheck className="size-5" aria-hidden />
          Administración
        </h1>
        <Link href="/" className="flex items-center gap-1 rounded-full px-3 py-1.5 text-sm hover:bg-white/15">
          <ArrowLeft className="size-4" aria-hidden />
          Volver a la app
        </Link>
      </header>
      <main className="mx-auto max-w-5xl p-4 pb-16">
        <p className="mb-4 text-sm text-ink-muted">
          Solo vos ves esta sección. Nadie más sabe que existe: para el resto, esta dirección da “página no
          encontrada”.
        </p>
        <nav aria-label="Secciones del panel" className="-mx-4 mb-4 overflow-x-auto px-4">
          <div role="tablist" className="flex w-max gap-1 rounded-xl bg-subtle p-1">
            {TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                role="tab"
                aria-selected={tab === t.id}
                onClick={() => setTab(t.id)}
                className={cn(
                  "min-h-10 rounded-lg px-3 text-sm whitespace-nowrap",
                  tab === t.id ? "bg-surface font-semibold text-ink shadow-sm" : "text-ink-muted hover:text-ink",
                )}
              >
                {t.label}
              </button>
            ))}
          </div>
        </nav>
        {overview.isError ? <Notice tone="error">{errorMessage(overview.error)}</Notice> : null}
        {overview.isPending ? <p className="text-sm text-ink-muted">Cargando…</p> : null}
        {overview.data ? <TabContent tab={tab} data={overview.data} now={overview.dataUpdatedAt} /> : null}
      </main>
    </div>
  );
}

function TabContent({ tab, data, now }: { tab: Tab; data: PlatformOverview; now: number }) {
  switch (tab) {
    case "summary":
      return <Summary data={data} now={now} />;
    case "organizations":
      return <Organizations orgs={data.organizations} />;
    case "people":
      return <People users={data.users} />;
    case "sessions":
      return <Sessions sessions={data.sessions} />;
    case "activity":
      return <Activity data={data} />;
  }
}

function Stat({ label, value, hint }: { label: string; value: number; hint?: string }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <p className="text-sm text-ink-muted">{label}</p>
      <p className="mt-1 text-2xl font-bold tabular-nums">{value}</p>
      {hint ? <p className="mt-1 text-xs text-ink-muted">{hint}</p> : null}
    </div>
  );
}

function Summary({ data, now }: { data: PlatformOverview; now: number }) {
  const paused = data.organizations.filter((o) => o.suspended_at).length;
  const suspended = data.users.filter((u) => !u.is_active).length;
  const recent = data.users.filter((u) => u.last_seen_at && now - new Date(u.last_seen_at).getTime() < RECENT_MS);
  const events = data.organizations.reduce((sum, o) => sum + o.events, 0);
  const budgets = data.organizations.reduce((sum, o) => sum + o.budgets, 0);
  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <Stat label="Organizaciones" value={data.organizations.length} hint={paused ? `${paused} pausada(s)` : undefined} />
        <Stat label="Personas" value={data.users.length} hint={suspended ? `${suspended} suspendida(s)` : undefined} />
        <Stat label="Usaron la app en la última hora" value={recent.length} />
        <Stat label="Sesiones abiertas" value={data.sessions.length} hint="Dispositivos con la sesión iniciada" />
        <Stat label="Eventos" value={events} />
        <Stat label="Presupuestos" value={budgets} />
      </div>
      <section>
        <h2 className="mb-2 font-semibold">Lo último que pasó</h2>
        <ActivityList items={data.activity.slice(0, 8)} />
      </section>
    </div>
  );
}

type AdminAction =
  | { kind: "user"; id: string; verb: "suspend" | "reactivate" }
  | { kind: "organization"; id: string; verb: "suspend" | "reactivate" }
  | { kind: "session"; id: string };

async function runAction(action: AdminAction): Promise<void> {
  switch (action.kind) {
    case "user": {
      const params = { path: { user_id: action.id } };
      unwrap(
        action.verb === "suspend"
          ? await api.POST("/api/v1/admin/users/{user_id}/suspend", { params })
          : await api.POST("/api/v1/admin/users/{user_id}/reactivate", { params }),
      );
      return;
    }
    case "organization": {
      const params = { path: { organization_id: action.id } };
      unwrap(
        action.verb === "suspend"
          ? await api.POST("/api/v1/admin/organizations/{organization_id}/suspend", { params })
          : await api.POST("/api/v1/admin/organizations/{organization_id}/reactivate", { params }),
      );
      return;
    }
    case "session":
      unwrap(await api.POST("/api/v1/admin/sessions/{session_id}/close", { params: { path: { session_id: action.id } } }));
  }
}

function useAdminAction() {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: runAction,
    onSettled: () => queryClient.invalidateQueries({ queryKey: OVERVIEW_KEY }),
  });
  const busy = (id: string) => mutation.isPending && mutation.variables?.id === id;
  return { ...mutation, busy };
}

function Organizations({ orgs }: { orgs: PlatformOrg[] }) {
  const action = useAdminAction();
  if (orgs.length === 0) return <p className="text-sm text-ink-muted">Todavía no hay organizaciones.</p>;
  return (
    <div className="flex flex-col gap-3">
      {action.isError ? <Notice tone="error">{errorMessage(action.error)}</Notice> : null}
      {orgs.map((org) => (
        <article key={org.id} className="rounded-xl border border-line bg-surface p-4">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="min-w-0">
              <h3 className="flex flex-wrap items-center gap-2 font-semibold">
                {org.name}
                {org.suspended_at ? (
                  <span className="rounded-full bg-danger-fill/10 px-2 py-0.5 text-xs font-semibold text-danger">
                    Pausada
                  </span>
                ) : null}
              </h3>
              <p className="text-xs text-ink-muted">
                Creada el {formatDateTime(org.created_at)} · Última actividad: {timeAgo(org.last_activity_at)}
              </p>
            </div>
            {org.suspended_at ? (
              <Button
                size="sm"
                variant="secondary"
                loading={action.busy(org.id)}
                onClick={() => action.mutate({ kind: "organization", id: org.id, verb: "reactivate" })}
              >
                Reactivar
              </Button>
            ) : (
              <Button
                size="sm"
                variant="danger"
                loading={action.busy(org.id)}
                onClick={() => {
                  if (
                    window.confirm(
                      `¿Pausar “${org.name}”? Nadie de esa organización va a poder usar Handie hasta que la reactives. No se borra nada.`,
                    )
                  )
                    action.mutate({ kind: "organization", id: org.id, verb: "suspend" });
                }}
              >
                Pausar
              </Button>
            )}
          </div>
          <p className="mt-2 text-sm">
            {org.events} evento(s) · {org.budgets} presupuesto(s) · {org.members.length} persona(s)
          </p>
          <ul className="mt-2 flex flex-col gap-1 text-sm">
            {org.members.map((m) => (
              <li key={m.user_id} className="flex flex-wrap gap-x-2 text-ink-muted">
                <span className="font-medium text-ink">{m.name}</span>
                <span>{m.email}</span>
                <span>· {roleLabel(m.role)}</span>
                {m.status !== "ACTIVE" ? <span>· {m.status === "DISABLED" ? "desactivada" : "invitada"}</span> : null}
              </li>
            ))}
          </ul>
        </article>
      ))}
    </div>
  );
}

function People({ users }: { users: PlatformUser[] }) {
  const action = useAdminAction();
  return (
    <div className="flex flex-col gap-3">
      {action.isError ? <Notice tone="error">{errorMessage(action.error)}</Notice> : null}
      {users.map((u) => (
        <article key={u.id} className="rounded-xl border border-line bg-surface p-4">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="min-w-0">
              <h3 className="flex flex-wrap items-center gap-2 font-semibold">
                {u.name}
                {u.is_me ? <span className="rounded-full bg-subtle px-2 py-0.5 text-xs">Vos</span> : null}
                {!u.is_active ? (
                  <span className="rounded-full bg-danger-fill/10 px-2 py-0.5 text-xs font-semibold text-danger">
                    Suspendida
                  </span>
                ) : null}
              </h3>
              <p className="truncate text-sm text-ink-muted">{u.email}</p>
            </div>
            {u.is_me ? null : u.is_active ? (
              <Button
                size="sm"
                variant="danger"
                loading={action.busy(u.id)}
                onClick={() => {
                  if (
                    window.confirm(
                      `¿Suspender a ${u.name}? Se le cierran todas las sesiones y no va a poder volver a entrar hasta que la reactives.`,
                    )
                  )
                    action.mutate({ kind: "user", id: u.id, verb: "suspend" });
                }}
              >
                Suspender
              </Button>
            ) : (
              <Button
                size="sm"
                variant="secondary"
                loading={action.busy(u.id)}
                onClick={() => action.mutate({ kind: "user", id: u.id, verb: "reactivate" })}
              >
                Reactivar
              </Button>
            )}
          </div>
          <p className="mt-2 text-sm text-ink-muted">
            Última entrada: {u.last_login_at ? formatDateTime(u.last_login_at) : "nunca"} · Usó la app{" "}
            {timeAgo(u.last_seen_at)} · {u.open_sessions} sesión(es) abierta(s)
          </p>
          {u.organizations.length ? (
            <p className="mt-1 text-sm">
              {u.organizations.map((o) => `${o.organization_name} (${roleLabel(o.role)})`).join(" · ")}
            </p>
          ) : (
            <p className="mt-1 text-sm text-ink-muted">Sin organización</p>
          )}
        </article>
      ))}
    </div>
  );
}

function Sessions({ sessions }: { sessions: PlatformSession[] }) {
  const action = useAdminAction();
  if (sessions.length === 0) return <p className="text-sm text-ink-muted">No hay sesiones abiertas.</p>;
  return (
    <div className="flex flex-col gap-2">
      {action.isError ? <Notice tone="error">{errorMessage(action.error)}</Notice> : null}
      {sessions.map((s) => (
        <article key={s.id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line bg-surface p-3">
          <div className="min-w-0">
            <p className="font-medium">
              {s.user_name} {s.is_current ? <span className="text-xs text-ink-muted">(esta sesión)</span> : null}
            </p>
            <p className="text-sm text-ink-muted">
              {describeDevice(s.user_agent)}
              {s.organization_name ? ` · ${s.organization_name}` : ""} · Activa {timeAgo(s.last_used_at)} · Abierta el{" "}
              {formatDateTime(s.created_at)}
            </p>
          </div>
          {s.is_current ? null : (
            <Button
              size="sm"
              variant="secondary"
              loading={action.busy(s.id)}
              onClick={() => {
                if (window.confirm(`¿Cerrar la sesión de ${s.user_name} en ${describeDevice(s.user_agent)}?`))
                  action.mutate({ kind: "session", id: s.id });
              }}
            >
              Cerrar sesión
            </Button>
          )}
        </article>
      ))}
    </div>
  );
}

function Activity({ data }: { data: PlatformOverview }) {
  const [org, setOrg] = useState("");
  const items = org ? data.activity.filter((a) => a.organization_name === org) : data.activity;
  const names = [...new Set(data.organizations.map((o) => o.name))];
  return (
    <div className="flex flex-col gap-3">
      {names.length > 1 ? (
        <label className="flex max-w-xs flex-col gap-1 text-sm font-medium">
          Organización
          <select
            value={org}
            onChange={(e) => setOrg(e.target.value)}
            className="h-10 rounded-lg border border-line bg-surface px-3"
          >
            <option value="">Todas</option>
            {names.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      <ActivityList items={items} />
    </div>
  );
}

function ActivityList({ items }: { items: PlatformOverview["activity"] }) {
  if (items.length === 0) return <p className="text-sm text-ink-muted">Todavía no hay actividad.</p>;
  return (
    <ul className="divide-y divide-line rounded-xl border border-line bg-surface">
      {items.map((a, i) => (
        <li key={`${a.created_at}-${i}`} className="flex flex-col gap-0.5 px-3 py-2 text-sm sm:flex-row sm:gap-3">
          <span className="shrink-0 text-ink-muted tabular-nums sm:w-36">{formatDateTime(a.created_at)}</span>
          <span className="min-w-0">
            <span className="font-medium">{a.user_name ?? (a.actor_type === "PUBLIC_TOKEN" ? "Un cliente" : "El sistema")}</span>{" "}
            {(ACTION_LABELS[a.action] ?? a.action).replace(/^./, (c) => c.toLowerCase())}
            <span className="text-ink-muted"> · {a.organization_name}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}
