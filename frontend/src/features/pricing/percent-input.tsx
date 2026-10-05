"use client";

import { useState } from "react";

import { TextField } from "@/components/ui/field";
import { fractionToPercentInput, percentToFraction } from "@/lib/parse/percent";

/** Campo de porcentaje: se escribe "3,5" y entrega la fracción "0.035" (string). */
export function PercentField({
  label,
  initial,
  onValue,
  hint,
  disabled,
  placeholder,
  hideLabel,
}: {
  label: string;
  hideLabel?: boolean;
  initial: string | null;
  onValue: (fraction: string | null, valid: boolean) => void;
  hint?: string;
  disabled?: boolean;
  placeholder?: string;
}) {
  const [raw, setRaw] = useState(initial === null ? "" : fractionToPercentInput(initial));
  const invalid = raw.trim() !== "" && percentToFraction(raw) === null;
  return (
    <TextField
      label={label}
      hideLabel={hideLabel}
      inputMode="decimal"
      autoComplete="off"
      value={raw}
      disabled={disabled}
      placeholder={placeholder}
      error={invalid ? "No es un porcentaje válido" : undefined}
      hint={hint}
      onChange={(e) => {
        setRaw(e.target.value);
        const fraction = e.target.value.trim() === "" ? null : percentToFraction(e.target.value);
        onValue(fraction, e.target.value.trim() === "" || fraction !== null);
      }}
    />
  );
}
