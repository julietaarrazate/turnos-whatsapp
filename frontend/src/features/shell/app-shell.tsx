"use client";

import { Camera, LogOut, Menu, Plus, Search, UserRound, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { HandieMark } from "@/components/brand/handie-logo";
import { ROLE_LABELS } from "@/features/auth/roles";
import { AppLock } from "@/features/account/app-lock";
import { PasskeyOffer } from "@/features/account/passkey-settings";
import { useSession } from "@/features/auth/session";
import { cn } from "@/lib/cn";

import { CommandPalette } from "./command-palette";
import { ActivityBell } from "@/features/activity/bell";
import { QuickPhotoDialog } from "@/features/pieces/quick-photo";
import { ShareApp } from "@/features/share/share-app";
import { ThemePicker } from "@/features/theme/theme";

import { NAV_ITEMS, isActive, mobileBar, moreItems } from "./nav";

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

/** El botón de salir queda al lado de la campana: sin preguntar, un toque de más cerraba la sesión. */
export function confirmLogout(logout: () => Promise<void>, ask: (message: string) => boolean = (m) => window.confirm(m)) {
  if (ask("¿Cerrar sesión? Vas a tener que volver a ingresar con tu mail y contraseña.")) void logout();
}

function openPalette() {
  window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", ctrlKey: true }));
}

/** Taller/montaje: sin menú ni "+", solo lo suyo. El servidor igual le niega todo lo demás. */
function CrewShell({ children }: { children: React.ReactNode }) {
  const { me, logout } = useSession();
  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-10 flex h-14 items-center gap-2 bg-bar px-4 text-white">
        <OrganizationSwitcher />
        <span className="truncate text-sm text-white/80">· {me.user.name}</span>
        <Link
          href="/settings/account"
          aria-label="Mi perfil"
          className="ml-auto flex size-11 shrink-0 items-center justify-center rounded-full bg-white/15 text-white"
        >
          <UserRound className="size-5" aria-hidden />
        </Link>
        <button
          type="button"
          onClick={() => confirmLogout(logout)}
          aria-label="Cerrar sesión"
          className="flex size-11 shrink-0 items-center justify-center rounded-full bg-white/15 text-white"
        >
          <LogOut className="size-5" aria-hidden />
        </button>
      </header>
      <AppLock />
      <main className="mx-auto w-full max-w-2xl px-4 pt-6 pb-10">
        <PasskeyOffer />
        {children}
      </main>
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
  const more = useRef<HTMLDialogElement>(null);
  const drawer = useRef<HTMLDialogElement>(null);
  const bar = mobileBar(can);
  const extra = moreItems(bar);
  const inMore = extra.some((item) => isActive(pathname, item.href));
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
        <div className="flex h-14 items-center gap-2 bg-bar px-4 text-white">
          <span className="min-w-0 flex-1">
            <OrganizationSwitcher />
          </span>
          <ActivityBell />
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
        <ShareApp className="mx-3 mb-2 w-auto" />
        <ThemePicker className="mx-3 mb-2" />
        <div className="flex items-center gap-2 border-t border-line p-3">
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium">{me.user.name}</p>
            <p className="truncate text-xs text-ink-muted">{me.role ? ROLE_LABELS[me.role] : null}</p>
          </div>
          <button
            type="button"
            onClick={() => confirmLogout(logout)}
            aria-label="Cerrar sesión"
            className="rounded-md p-2 text-ink-muted hover:bg-subtle hover:text-ink"
          >
            <LogOut className="size-4" aria-hidden />
          </button>
        </div>
      </aside>

      {/* Header (mobile) */}
      <header className="sticky top-0 z-10 flex h-14 items-center gap-2 bg-bar px-2 text-white lg:hidden">
        <button
          type="button"
          aria-label="Abrir menú"
          onClick={() => drawer.current?.showModal()}
          className="flex size-11 shrink-0 items-center justify-center rounded-full hover:bg-white/15"
        >
          <Menu className="size-6" aria-hidden />
        </button>
        <span className="min-w-0 flex-1 truncate">
          <OrganizationSwitcher />
        </span>
        <ActivityBell />
      </header>

      {/* Menú desplegable (mobile): todas las secciones, la organización, el tema y la cuenta */}
      <dialog
        ref={drawer}
        aria-label="Menú"
        onClick={(event) => event.target === drawer.current && drawer.current?.close()}
        className="m-0 h-dvh max-h-none w-[85vw] max-w-xs border-0 bg-surface p-0 backdrop:bg-black/40 lg:hidden"
      >
        <div className="flex h-full flex-col">
          <div className="flex h-14 shrink-0 items-center gap-2 bg-bar px-3 text-white">
            <HandieMark className="size-8" />
            <span className="flex-1 text-lg font-extrabold tracking-tight">
              handie<span className="text-magenta">.</span>
            </span>
            <button
              type="button"
              aria-label="Cerrar menú"
              onClick={() => drawer.current?.close()}
              className="flex size-10 items-center justify-center rounded-full hover:bg-white/15"
            >
              <X className="size-5" aria-hidden />
            </button>
          </div>
          <nav aria-label="Secciones" className="flex-1 overflow-y-auto p-2">
            <ul className="flex flex-col gap-0.5">
              {[...NAV_ITEMS, { href: "/settings/account", label: "Mi perfil", icon: UserRound }].map(({ href, label, icon: Icon }) => (
                <li key={href}>
                  <Link
                    href={href}
                    onClick={() => drawer.current?.close()}
                    aria-current={isActive(pathname, href) ? "page" : undefined}
                    className={cn(
                      "flex min-h-12 items-center gap-3 rounded-xl px-3 text-base",
                      isActive(pathname, href) ? "bg-brand/[0.08] font-semibold text-brand" : "text-ink hover:bg-subtle",
                    )}
                  >
                    <Icon className="size-5" aria-hidden />
                    {label}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
          <div className="flex shrink-0 flex-col gap-3 border-t border-line p-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))]">
            {me.memberships.length > 1 ? (
              <label className="flex flex-col gap-1 text-xs font-semibold text-ink-muted">
                Organización
                <OrganizationSwitcher />
              </label>
            ) : null}
            <ThemePicker />
            <div className="flex items-center gap-3">
              <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-fill text-sm font-bold text-white">
                {me.user.name.trim().charAt(0).toUpperCase()}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate font-semibold">{me.user.name}</p>
                <p className="truncate text-xs text-ink-muted">{me.role ? ROLE_LABELS[me.role] : null}</p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => confirmLogout(logout)}
              className="flex min-h-11 items-center gap-2 rounded-xl px-3 text-base font-semibold text-danger hover:bg-danger/10"
            >
              <LogOut className="size-5" aria-hidden /> Cerrar sesión
            </button>
          </div>
        </div>
      </dialog>

      <AppLock />
      <main className="mx-auto w-full max-w-5xl px-4 pt-6 pb-28 lg:px-8 lg:pb-10">
        <PasskeyOffer />
        {children}
      </main>

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
          {[byHref(bar.right)].map(({ href, label, icon: Icon }) => (
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
          <li>
            <button
              type="button"
              onClick={() => more.current?.showModal()}
              className={cn(
                "flex h-full w-full flex-col items-center justify-center gap-0.5 text-xs font-semibold",
                inMore ? "text-brand" : "text-ink-muted",
              )}
            >
              <Menu className="size-6" aria-hidden />
              Más
            </button>
          </li>
        </ul>
      </nav>

      {/* "Más": todas las secciones que no entran en la barra */}
      <dialog
        ref={more}
        aria-label="Más secciones"
        onClick={(event) => event.target === more.current && more.current?.close()}
        className="m-0 mt-auto w-full max-w-none rounded-t-2xl border-0 bg-surface p-0 backdrop:bg-black/40"
      >
        <div className="mx-auto my-3 h-1 w-10 rounded-full bg-line" aria-hidden />
        <nav aria-label="Más secciones" className="px-4 pb-[calc(1.5rem+env(safe-area-inset-bottom))]">
          <ul className="grid grid-cols-3 gap-2">
            {extra.map(({ href, label, icon: Icon }) => (
              <li key={href}>
                <Link
                  href={href}
                  onClick={() => more.current?.close()}
                  aria-current={isActive(pathname, href) ? "page" : undefined}
                  className={cn(
                    "flex h-20 flex-col items-center justify-center gap-1.5 rounded-xl border text-sm font-semibold",
                    isActive(pathname, href) ? "border-brand bg-brand/[0.06] text-brand" : "border-line text-ink",
                  )}
                >
                  <Icon className="size-6" aria-hidden />
                  {label}
                </Link>
              </li>
            ))}
          </ul>
          <p className="mt-4 mb-1.5 text-xs font-semibold text-ink-muted">Apariencia</p>
          <ThemePicker />
          <ShareApp className="mt-4" />
        </nav>
      </dialog>

      {/* Bottom sheet de acciones rápidas */}
      <dialog
        ref={quickActions}
        aria-label="Crear"
        onClick={(event) => event.target === quickActions.current && quickActions.current?.close()}
        className="m-0 mt-auto w-full max-w-none rounded-t-2xl border-0 bg-surface p-0 backdrop:bg-black/40"
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
          className="fixed inset-x-4 bottom-[calc(5.5rem+env(safe-area-inset-bottom))] z-20 rounded-xl bg-ink px-4 py-3 text-center text-sm font-semibold text-surface shadow-lg lg:inset-x-auto lg:right-6 lg:bottom-6"
        >
          Avance enviado
        </p>
      ) : null}

      <CommandPalette />
    </div>
  );
}
