import type { TaxCondition } from "@/lib/api/types";

export const TAX_CONDITION_LABELS: Record<TaxCondition, string> = {
  RI: "Responsable Inscripto",
  MONOTRIBUTO: "Monotributo",
  EXENTO: "Exento",
};

export const TAX_CONDITION_OPTIONS = [
  { value: "", label: "Sin especificar" },
  ...Object.entries(TAX_CONDITION_LABELS).map(([value, label]) => ({ value, label })),
];
