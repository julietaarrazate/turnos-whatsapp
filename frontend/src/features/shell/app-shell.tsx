"use client";

import { Camera, LogOut, Plus, Search } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { ROLE_LABELS } from "@/features/auth/roles";
import { useSession } from "@/features/auth/session";
import { cn } from "@/lib/cn";

import { CommandPalette } from "./command-palette";
import { QuickPhotoDialog } from "@/features/pieces/quick-photo";

import { NAV_ITEMS, isActive, mobileBar } from "./nav";

const QUICK_ACTIONS: { label: string; href?: string; phase?: number }[] = [
  { label: "Nuevo presupuesto", href: "/budgets/new" },
  { label: "Nuevo cliente", href: "/clients/new" },
  { label: "Nuevo producto", href: "/catalog/new" },
  { label: "Nuevo gasto", href: "/events" }, // se carga desde la pestaña Gastos del evento
];

function OrganizationSwitcher() {
  const { me, switchOrganization } = useSession();
  const [pending, setPending] = useState(false);
  const active = me.memberships.find((m) => m.organization_id === me.active_organization_id);

  if (me.memberships.length <= 1) {
    return <span className="truncate text-base font-bold tracking-tight">{active?.organization_name}</span>;
  }
  return (
    <select
      aria-label="Organización"
      value={me.active_organization_id ?? ""}
      disabled={pending}
      onChange={async (event) => {
        setPending(true);
        try {
          await switchOrganization(event.target.value);
        } finally {
          setPending(false);
        }
      }}
      className="max-w-48 truncate rounded-md border border-line bg-surface px-2 py-1 text-sm font-semibold text-ink"
    >
      {me.memberships.map((m) => (
        <option key={m.organization_id} value={m.organization_id}>
          {m.organization_name}
        </option>
      ))}
    </select>
  );
}

function openPalette() {
  window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", ctrlKey: true }));
}

/** Taller/montaje: sin menú ni "+", solo lo suyo. El servidor igual le niega todo lo demás. */
function CrewShell({ children }: { children: React.ReactNode }) {
  const { me, logout } = useSession();
  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-10 flex h-14 items-center gap-2 bg-brand px-4 text-white">
        <OrganizationSwitcher />
        <span className="truncate text-sm text-white/80">· {me.user.name}</span>
        <button
          type="button"
          onClick={logout}
          aria-label="Cerrar sesión"
          className="ml-auto flex size-11 shrink-0 items-center justify-center rounded-full bg-white/15 text-white"
        >
          <LogOut className="size-5" aria-hidden />
        </button>
      </header>
      <main className="mx-auto w-full max-w-2xl px-4 pt-6 pb-10">{children}</main>
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const { can } = useSession();
  if (!can("org.view")) return <CrewShell>{children}</CrewShell>;
  return <FullShell>{children}</FullShell>;
}

function FullShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { me, logout, can } = useSession();
  const quickActions = useRef<HTMLDialogElement>(null);
  const bar = mobileBar(can);
  const byHref = (href: string) => NAV_ITEMS.find((item) => item.href === href)!;
  const [photo, setPhoto] = useState(false);
  const [sent, setSent] = useState(false);
  const canPhoto = can("production.manage");
  useEffect(() => {
    if (!sent) return;
    const timer = window.setTimeout(() => setSent(false), 3500);
    return () => window.clearTimeout(timer);
  }, [sent]);

  return (
    <div className="min-h-dvh lg:pl-60">
      {/* Sidebar (desktop) */}
      <aside className="fixed inset-y-0 left-0 hidden w-60 flex-col border-r border-line bg-surface lg:flex">
        <div className="flex h-14 items-center bg-brand px-4 text-white">
          <OrganizationSwitcher />
        </div>
        <button
          type="button"
          onClick={openPalette}
          className="mx-3 mt-3 flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-sm text-ink-muted hover:bg-subtle"
        >
          <Search className="size-4" aria-hidden />
          Buscar
          <kbd className="ml-auto text-xs">⌘K</kbd>
        </button>
        {canPhoto ? (
          <button
            type="button"
            onClick={() => setPhoto(true)}
            className="mx-3 mt-2 flex items-center gap-2 rounded-lg bg-magenta px-3 py-2 text-sm font-semibold text-white hover:bg-magenta/90"
          >
            <Camera className="size-4" aria-hidden />
            Foto de avance
          </button>
        ) : null}
        <nav aria-label="Principal" className="flex-1 overflow-y-auto p-3">
          <ul className="flex flex-col gap-0.5">
            {NAV_ITEMS.map(({ href, label, icon: Icon, phase }) => (
              <li key={href}>
                <Link
                  href={href}
                  aria-current={isActive(pathname, href) ? "page" : undefined}
                  className={cn(
                    "flex items-center gap-3 rounded-lg px-3 py-2 text-sm",
                    isActive(pathname, href)
                      ? "bg-subtle font-medium text-ink"
                      : "text-ink-muted hover:bg-subtle hover:text-ink",
                  )}
                >
                  <Icon className="size-4" aria-hidden />
                  {label}
                  {phase ? (
                    <span className="ml-auto rounded bg-subtle px-1.5 text-[10px] text-ink-muted">Pronto</span>
                  ) : null}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
        <div className="flex items-center gap-2 border-t border-line p-3">
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium">{me.user.name}</p>
            <p className="truncate text-xs text-ink-muted">{me.role ? ROLE_LABELS[me.role] : null}</p>
          </div>
          <button
            type="button"
            onClick={logout}
            aria-label="Cerrar sesión"
            className="rounded-md p-2 text-ink-muted hover:bg-subtle hover:text-ink"
          >
            <LogOut className="size-4" aria-hidden />
          </button>
        </div>
      </aside>

      {/* Header (mobile) */}
      <header className="sticky top-0 z-10 flex h-14 items-center gap-2 bg-brand px-4 text-white lg:hidden">
        <OrganizationSwitcher />
        <button
          type="button"
          onClick={logout}
          aria-label="Cerrar sesión"
          className="ml-auto flex size-11 items-center justify-center rounded-full bg-white/15 text-white"
        >
          <LogOut className="size-5" aria-hidden />
        </button>
      </header>

      <main className="mx-auto w-full max-w-5xl px-4 pt-6 pb-28 lg:px-8 lg:pb-10">{children}</main>

      {/* Barra inferior (mobile): al alcance del pulgar */}
      <nav
        aria-label="Principal"
        className="fixed inset-x-0 bottom-0 z-10 border-t border-line bg-surface pb-[env(safe-area-inset-bottom)] lg:hidden"
      >
        <ul className="grid h-[4.5rem] grid-cols-5">
          {bar.left.map(byHref).map(({ href, label, icon: Icon }) => (
            <li key={href}>
              <Link
                href={href}
                aria-current={isActive(pathname, href) ? "page" : undefined}
                className={cn(
                  "flex h-full flex-col items-center justify-center gap-0.5 text-xs font-semibold",
                  isActive(pathname, href) ? "text-brand" : "text-ink-muted",
                )}
              >
                <Icon className="size-6" aria-hidden />
                {label}
              </Link>
            </li>
          ))}
          <li className="flex items-center justify-center">
            {bar.center === "camera" ? (
              <button
                type="button"
                aria-label="Foto de avance"
                onClick={() => setPhoto(true)}
                className="flex size-14 items-center justify-center rounded-full bg-magenta text-white shadow-lg shadow-magenta/40"
              >
                <Camera className="size-6" aria-hidden />
              </button>
            ) : (
              <button
                type="button"
                aria-label="Crear"
                onClick={() => quickActions.current?.showModal()}
                className="flex size-14 items-center justify-center rounded-full bg-magenta text-white shadow-lg shadow-magenta/40"
              >
                <Plus className="size-6" aria-hidden />
              </button>
            )}
          </li>
          {[byHref(bar.right), { href: "/settings", label: "Más", icon: NAV_ITEMS.at(-1)!.icon }].map(
            ({ href, label, icon: Icon }) => (
              <li key={href}>
                <Link
                  href={href}
                  aria-current={isActive(pathname, href) ? "page" : undefined}
                  className={cn(
                    "flex h-full flex-col items-center justify-center gap-0.5 text-xs font-semibold",
                    isActive(pathname, href) ? "text-brand" : "text-ink-muted",
                  )}
                >
                  <Icon className="size-6" aria-hidden />
                  {label}
                </Link>
              </li>
            ),
          )}
        </ul>
      </nav>

      {/* Bottom sheet de acciones rápidas */}
      <dialog
        ref={quickActions}
        aria-label="Crear"
        onClick={(event) => event.target === quickActions.current && quickActions.current?.close()}
        className="m-0 mt-auto w-full max-w-none rounded-t-2xl border-0 bg-surface p-0 backdrop:bg-ink/30"
      >
        <div className="mx-auto my-3 h-1 w-10 rounded-full bg-line" aria-hidden />
        <ul className="px-4 pb-[calc(1.5rem+env(safe-area-inset-bottom))]">
          {canPhoto ? (
            <li>
              <button
                type="button"
                onClick={() => {
                  quickActions.current?.close();
                  setPhoto(true);
                }}
                className="flex h-12 w-full items-center gap-2 border-b border-line text-left text-base font-semibold text-magenta"
              >
                <Camera className="size-5" aria-hidden /> Foto de avance
              </button>
            </li>
          ) : null}
          {QUICK_ACTIONS.map((action) => (
            <li key={action.label}>
              {action.href ? (
                <Link
                  href={action.href}
                  onClick={() => quickActions.current?.close()}
                  className="flex h-12 w-full items-center border-b border-line text-base text-ink"
                >
                  {action.label}
                </Link>
              ) : (
                <button
                  type="button"
                  disabled
                  className="flex h-12 w-full items-center justify-between border-b border-line text-left text-base text-ink-muted"
                >
                  {action.label}
                  <span className="text-xs">Fase {action.phase}</span>
                </button>
              )}
            </li>
          ))}
        </ul>
      </dialog>

      {canPhoto ? <QuickPhotoDialog open={photo} onClose={() => setPhoto(false)} onSent={() => setSent(true)} /> : null}
      {sent ? (
        <p
          role="status"
          className="fixed inset-x-4 bottom-[calc(5.5rem+env(safe-area-inset-bottom))] z-20 rounded-xl bg-ink px-4 py-3 text-center text-sm font-semibold text-white shadow-lg lg:inset-x-auto lg:right-6 lg:bottom-6"
        >
          Avance enviado
        </p>
      ) : null}

      <CommandPalette />
    </div>
  );
}
