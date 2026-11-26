"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";

import { cn } from "@/lib/cn";

export type ThemeChoice = "system" | "light" | "dark";

const KEY = "theme";

export function readTheme(storage: Pick<Storage, "getItem"> | undefined): ThemeChoice {
  try {
    const value = storage?.getItem(KEY);
    return value === "light" || value === "dark" ? value : "system";
  } catch {
    return "system"; // navegación privada o almacenamiento bloqueado
  }
}

/** "Automático" sigue al teléfono (lo resuelve el CSS); Claro u Oscuro lo fijan en <html>. */
export function applyTheme(choice: ThemeChoice, root: HTMLElement = document.documentElement): void {
  if (choice === "system") delete root.dataset.theme;
  else root.dataset.theme = choice;
}

/** Aplica lo elegido apenas carga la app (la preferencia vive en este dispositivo). */
export function ThemeSync() {
  useEffect(() => applyTheme(readTheme(window.localStorage)), []);
  return null;
}

const OPTIONS: { value: ThemeChoice; label: string; icon: typeof Sun }[] = [
  { value: "light", label: "Claro", icon: Sun },
  { value: "dark", label: "Oscuro", icon: Moon },
  { value: "system", label: "Automático", icon: Monitor },
];

/** Claro / Oscuro / Automático (como el teléfono). Se guarda en este dispositivo. */
export function ThemePicker({ className }: { className?: string }) {
  const [choice, setChoice] = useState<ThemeChoice>("system");
  useEffect(() => setChoice(readTheme(window.localStorage)), []); // eslint-disable-line react-hooks/set-state-in-effect -- se lee del dispositivo al montar
  return (
    <div role="group" aria-label="Apariencia" className={cn("grid grid-cols-3 gap-1 rounded-lg bg-subtle p-1", className)}>
      {OPTIONS.map(({ value, label, icon: Icon }) => (
        <button
          key={value}
          type="button"
          aria-pressed={choice === value}
          onClick={() => {
            setChoice(value);
            try {
              if (value === "system") window.localStorage.removeItem(KEY);
              else window.localStorage.setItem(KEY, value);
            } catch {
              // sin almacenamiento: se aplica igual, solo por esta vez
            }
            applyTheme(value);
          }}
          className={cn(
            "flex h-9 items-center justify-center gap-1.5 rounded-md text-xs font-semibold",
            choice === value ? "bg-surface text-ink shadow-sm" : "text-ink-muted",
          )}
        >
          <Icon className="size-4" aria-hidden />
          {label}
        </button>
      ))}
    </div>
  );
}
