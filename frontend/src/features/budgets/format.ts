import { formatQuantity } from "@/lib/format/number";
import { parseDecimalAR } from "@/lib/parse/number";
import { fractionToPercentInput, percentToFraction } from "@/lib/parse/percent";

/** Cantidades y porcentajes para los CommitField (strings decimales, sin floats). */
export const quantityField = {
  display: (value: string) => formatQuantity(value),
  parse: (text: string) => {
    const value = parseDecimalAR(text);
    return value !== null && value !== "0" ? value : undefined;
  },
};

export const moneyField = {
  display: (value: string) => formatQuantity(value),
  parse: (text: string) => parseDecimalAR(text) ?? undefined,
};

export const daysField = {
  display: (value: number) => String(value),
  parse: (text: string) => {
    const n = Number.parseInt(text, 10);
    return Number.isInteger(n) && n >= 1 && n <= 365 && /^\d+$/.test(text.trim()) ? n : undefined;
  },
};

/** Porcentaje opcional: vacío = null (usar la regla). */
export const optionalPercentField = {
  display: (value: string | null) => (value === null ? "" : fractionToPercentInput(value)),
  parse: (text: string): string | null | undefined => (text.trim() === "" ? null : (percentToFraction(text) ?? undefined)),
};

export const percentField = {
  display: (value: string) => fractionToPercentInput(value),
  parse: (text: string) => (text.trim() === "" ? "0" : (percentToFraction(text) ?? undefined)),
};
