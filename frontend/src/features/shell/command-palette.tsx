"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { cn } from "@/lib/cn";

import { NAV_ITEMS } from "./nav";

const SETTINGS_ITEMS = [
  { href: "/settings/organization", label: "Configuración · Organización" },
  { href: "/settings/pricing", label: "Configuración · Pricing" },
  { href: "/settings/members", label: "Configuración · Usuarios y roles" },
  { href: "/settings/audit", label: "Configuración · Auditoría" },
];

function normalize(text: string): string {
  return text.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
}

/** ⌘K / Ctrl+K. Hoy navega por secciones; en la Fase 2 suma clientes, eventos y productos. */
export function CommandPalette() {
  const router = useRouter();
  const dialog = useRef<HTMLDialogElement>(null);
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);

  const items = useMemo(() => {
    const all = [...NAV_ITEMS.map(({ href, label }) => ({ href, label })), ...SETTINGS_ITEMS];
    const q = normalize(query.trim());
    return q ? all.filter((item) => normalize(item.label).includes(q)) : all;
  }, [query]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setQuery("");
        setCursor(0);
        dialog.current?.showModal();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  function go(href: string) {
    dialog.current?.close();
    router.push(href);
  }

  return (
    <dialog
      ref={dialog}
      aria-label="Buscar"
      className="m-auto mt-[15vh] w-[min(36rem,calc(100vw-2rem))] rounded-xl border border-line bg-surface p-0 shadow-2xl backdrop:bg-ink/30"
    >
      <input
        autoFocus
        value={query}
        onChange={(event) => {
          setQuery(event.target.value);
          setCursor(0);
        }}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown") {
            event.preventDefault();
            setCursor((c) => Math.min(c + 1, items.length - 1));
          } else if (event.key === "ArrowUp") {
            event.preventDefault();
            setCursor((c) => Math.max(c - 1, 0));
          } else if (event.key === "Enter" && items[cursor]) {
            go(items[cursor].href);
          }
        }}
        placeholder="Buscar sección…"
        aria-label="Buscar sección"
        className="h-12 w-full border-b border-line bg-transparent px-4 text-base outline-none"
      />
      <ul role="listbox" className="max-h-80 overflow-y-auto p-2">
        {items.map((item, index) => (
          <li key={item.href} role="option" aria-selected={index === cursor}>
            <button
              type="button"
              onClick={() => go(item.href)}
              onMouseEnter={() => setCursor(index)}
              className={cn(
                "w-full rounded-lg px-3 py-2 text-left text-sm",
                index === cursor ? "bg-subtle text-ink" : "text-ink-muted",
              )}
            >
              {item.label}
            </button>
          </li>
        ))}
        {items.length === 0 ? <li className="px-3 py-2 text-sm text-ink-muted">Sin resultados</li> : null}
      </ul>
    </dialog>
  );
}
