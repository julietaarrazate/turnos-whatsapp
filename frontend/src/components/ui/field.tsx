import { Eye, EyeOff } from "lucide-react";
import {
  forwardRef,
  useId,
  useState,
  type InputHTMLAttributes,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";

import { cn } from "@/lib/cn";

const control =
  "w-full rounded-lg border border-line bg-surface px-3 text-base text-ink placeholder:text-ink-muted " +
  "focus:border-accent focus:outline-2 focus:outline-accent/30 disabled:bg-subtle sm:text-sm";

interface FieldShellProps {
  label: string;
  hideLabel?: boolean;
  hint?: string;
  error?: string;
  id: string;
  children: React.ReactNode;
}

function FieldShell({ label, hideLabel, hint, error, id, children }: FieldShellProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className={hideLabel ? "sr-only" : "text-sm font-medium text-ink"}>
        {label}
      </label>
      {children}
      {error ? (
        <p id={`${id}-error`} className="text-sm text-danger" role="alert">
          {error}
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} className="text-sm text-ink-muted">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

export interface TextFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  /** La etiqueta solo la leen los lectores de pantalla (filas donde el contexto ya es visible). */
  hideLabel?: boolean;
  hint?: string;
  error?: string;
}

export const TextField = forwardRef<HTMLInputElement, TextFieldProps>(function TextField(
  { label, hideLabel, hint, error, className, id, ...props },
  ref,
) {
  const autoId = useId();
  const fieldId = id ?? autoId;
  return (
    <FieldShell label={label} hideLabel={hideLabel} hint={hint} error={error} id={fieldId}>
      <input
        ref={ref}
        id={fieldId}
        className={cn(control, "h-11 sm:h-10", error && "border-danger", className)}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${fieldId}-error` : hint ? `${fieldId}-hint` : undefined}
        {...props}
      />
    </FieldShell>
  );
});

export type PasswordFieldProps = Omit<TextFieldProps, "type">;

/** Contraseña con botón para mostrarla (en el celular es fácil equivocarse al tipear). */
export const PasswordField = forwardRef<HTMLInputElement, PasswordFieldProps>(function PasswordField(
  { label, hideLabel, hint, error, className, id, ...props },
  ref,
) {
  const autoId = useId();
  const fieldId = id ?? autoId;
  const [visible, setVisible] = useState(false);
  const Icon = visible ? EyeOff : Eye;
  return (
    <FieldShell label={label} hideLabel={hideLabel} hint={hint} error={error} id={fieldId}>
      <div className="relative">
        <input
          ref={ref}
          id={fieldId}
          type={visible ? "text" : "password"}
          className={cn(control, "h-11 pr-11 sm:h-10", error && "border-danger", className)}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${fieldId}-error` : hint ? `${fieldId}-hint` : undefined}
          {...props}
        />
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          aria-label="Mostrar contraseña"
          aria-pressed={visible}
          aria-controls={fieldId}
          className="absolute inset-y-0 right-0 flex w-11 items-center justify-center rounded-r-lg text-ink-muted hover:text-ink focus-visible:outline-2 focus-visible:outline-accent/30"
        >
          <Icon className="size-4" aria-hidden />
        </button>
      </div>
    </FieldShell>
  );
});

export interface SelectFieldProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label: string;
  hint?: string;
  error?: string;
  options: { value: string; label: string }[];
}

export function SelectField({ label, hint, error, options, id, className, ...props }: SelectFieldProps) {
  const autoId = useId();
  const fieldId = id ?? autoId;
  return (
    <FieldShell label={label} hint={hint} error={error} id={fieldId}>
      <select id={fieldId} className={cn(control, "h-11 sm:h-10", className)} {...props}>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </FieldShell>
  );
}

export interface TextAreaFieldProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label: string;
  hint?: string;
  error?: string;
}

export function TextAreaField({ label, hint, error, id, className, rows = 3, ...props }: TextAreaFieldProps) {
  const autoId = useId();
  const fieldId = id ?? autoId;
  return (
    <FieldShell label={label} hint={hint} error={error} id={fieldId}>
      <textarea id={fieldId} rows={rows} className={cn(control, "py-2", className)} {...props} />
    </FieldShell>
  );
}

export function CheckboxField({
  label,
  className,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label: string }) {
  return (
    <label className={cn("flex min-h-11 items-center gap-2 text-sm text-ink sm:min-h-10", className)}>
      <input type="checkbox" className="size-4 accent-accent" {...props} />
      {label}
    </label>
  );
}
