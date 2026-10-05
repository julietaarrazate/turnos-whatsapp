import { parseDecimalAR } from "./number";

/**
 * Porcentaje escrito por la persona ("30", "3,5", "12,75 %") → fracción como string ("0.3",
 * "0.035", "0.1275"). Corre la coma dos lugares sobre el string: sin floats.
 */
export function percentToFraction(raw: string): string | null {
  const value = parseDecimalAR(raw.replace(/%/g, ""));
  if (value === null) return null;
  const [int, frac = ""] = value.split(".");
  // Mover la coma dos lugares a la izquierda: "3.5" → dígitos "35", coma en la posición -1.
  const point = int.length - 2;
  const digits = point > 0 ? int + frac : "0".repeat(1 - point) + int + frac;
  const at = Math.max(point, 1);
  const whole = digits.slice(0, at).replace(/^0+(?=\d)/, "");
  const decimals = digits.slice(at).replace(/0+$/, "");
  return decimals ? `${whole}.${decimals}` : whole;
}

/** Fracción ("0.035000") → texto editable en es-AR ("3,5"). */
export function fractionToPercentInput(fraction: string): string {
  const [int, frac = ""] = fraction.split(".");
  const digits = int + frac.padEnd(2, "0");
  const whole = digits.slice(0, int.length + 2).replace(/^0+(?=\d)/, "");
  const decimals = digits.slice(int.length + 2).replace(/0+$/, "");
  return decimals ? `${whole},${decimals}` : whole;
}
