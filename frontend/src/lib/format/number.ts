/**
 * Formato es-AR sobre strings decimales, SIN convertir a float (el dinero es exacto).
 * Los valores llegan ya calculados y redondeados por el servidor; acá solo se presentan.
 */

export type DecimalString = string;

const DECIMAL_RE = /^-?\d+(\.\d+)?$/;

function splitDecimal(value: DecimalString): { negative: boolean; int: string; frac: string } {
  if (!DECIMAL_RE.test(value)) throw new Error(`Número inválido: ${value}`);
  const negative = value.startsWith("-");
  const [int, frac = ""] = (negative ? value.slice(1) : value).split(".");
  return { negative, int: int.replace(/^0+(?=\d)/, ""), frac };
}

function groupThousands(int: string): string {
  return int.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}

/** Redondeo HALF_UP sobre dígitos (solo para mostrar; nunca para calcular). */
function roundDigits(int: string, frac: string, decimals: number): { int: string; frac: string } {
  if (frac.length <= decimals) return { int, frac: frac.padEnd(decimals, "0") };
  const keep = int + frac.slice(0, decimals);
  const roundUp = Number(frac[decimals]) >= 5;
  let digits = keep;
  if (roundUp) {
    const chars = keep.split("");
    let i = chars.length - 1;
    while (i >= 0) {
      if (chars[i] === "9") {
        chars[i] = "0";
        i -= 1;
      } else {
        chars[i] = String(Number(chars[i]) + 1);
        break;
      }
    }
    digits = (i < 0 ? "1" : "") + chars.join("");
  }
  const cut = digits.length - decimals;
  return { int: digits.slice(0, cut) || "0", frac: digits.slice(cut) };
}

export function formatDecimal(value: DecimalString, decimals = 2): string {
  const { negative, int, frac } = splitDecimal(value);
  const rounded = roundDigits(int, frac, decimals);
  const isZero = /^0*$/.test(rounded.int + rounded.frac);
  const body = groupThousands(rounded.int) + (decimals > 0 ? `,${rounded.frac}` : "");
  return negative && !isZero ? `-${body}` : body;
}

export function formatMoney(value: DecimalString, currency = "ARS", decimals = 2): string {
  const symbol = currency === "ARS" ? "$" : currency === "USD" ? "US$" : currency;
  const formatted = formatDecimal(value, decimals);
  return formatted.startsWith("-") ? `-${symbol} ${formatted.slice(1)}` : `${symbol} ${formatted}`;
}

/** Una fracción ("0.2308") como porcentaje ("23,1 %"). */
export function formatPercent(fraction: DecimalString, decimals = 1): string {
  const { negative, int, frac } = splitDecimal(fraction);
  const digits = int + frac.padEnd(2, "0");
  const shifted = { int: digits.slice(0, int.length + 2), frac: digits.slice(int.length + 2) };
  const sign = negative ? "-" : "";
  return `${formatDecimal(`${sign}${shifted.int}${shifted.frac ? `.${shifted.frac}` : ""}`, decimals)} %`;
}
