"use client";

import { useRef, useState } from "react";

import { cn } from "@/lib/cn";

/**
 * Input que muestra lo tipeado al instante y guarda al salir del campo o con Enter (no en cada
 * tecla). `parse` devuelve el valor para la API o `undefined` si el texto no es válido.
 */
export function CommitField<T>({
  value,
  display,
  parse,
  onCommit,
  label,
  hideLabel = true,
  className,
  inputMode = "decimal",
  disabled,
  placeholder,
  suffix,
}: {
  value: T;
  display: (value: T) => string;
  parse: (text: string) => T | undefined;
  onCommit: (value: T) => void;
  label: string;
  hideLabel?: boolean;
  className?: string;
  inputMode?: "decimal" | "numeric" | "text";
  disabled?: boolean;
  placeholder?: string;
  suffix?: string;
}) {
  // Mientras se edita, el texto es local; fuera del foco se muestra siempre el valor del servidor.
  const [draft, setDraft] = useState<string | null>(null);
  const cancelled = useRef(false);
  const text = draft ?? display(value);
  const parsed = parse(text);
  const invalid = parsed === undefined;

  function commit() {
    setDraft(null);
    if (cancelled.current) {
      cancelled.current = false;
      return;
    }
    if (parsed !== undefined && display(parsed) !== display(value)) onCommit(parsed);
  }

  return (
    <label className={cn("flex flex-col gap-1", className)}>
      <span className={hideLabel ? "sr-only" : "text-xs text-ink-muted"}>{label}</span>
      <span className="relative flex items-center">
        <input
          value={text}
          inputMode={inputMode}
          disabled={disabled}
          placeholder={placeholder}
          aria-invalid={invalid || undefined}
          onFocus={(e) => {
            setDraft(display(value));
            e.currentTarget.select();
          }}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === "Enter") e.currentTarget.blur();
            if (e.key === "Escape") {
              cancelled.current = true; // Esc descarta lo tipeado
              e.currentTarget.blur();
            }
          }}
          className={cn(
            "h-10 w-full rounded-lg border border-line bg-surface px-2 text-right text-base tabular-nums sm:h-9 sm:text-sm",
            "focus:border-accent focus:outline-2 focus:outline-accent/30 disabled:bg-subtle",
            suffix && "pr-7",
            invalid && "border-danger",
          )}
        />
        {suffix ? <span className="pointer-events-none absolute right-2 text-xs text-ink-muted">{suffix}</span> : null}
      </span>
    </label>
  );
}
