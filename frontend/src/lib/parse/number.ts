/**
 * Parser numérico es-AR (PRODUCT_SPEC §7.1). Devuelve un string decimal normalizado
 * ("1234.5") o null si la entrada no es un número válido. Nunca devuelve float: el dinero
 * viaja como string hasta el servidor, que es quien calcula.
 *
 * Reglas:
 * - "," es separador decimal y "." de miles: "1.234,5" → "1234.5"; "1,5" → "1.5".
 * - Un único "." seguido de exactamente 3 dígitos es separador de miles: "1.500" → "1500".
 * - Un único "." seguido de 1, 2 o más de 3 dígitos es decimal (teclados numéricos de
 *   celular que solo tienen "."): "1.5" → "1.5"; "12.75" → "12.75".
 * - Si aparecen "." y ",", el que va último es el decimal: "1,234.5" → "1234.5".
 * - Se aceptan "$", espacios y un signo "-" inicial (si allowNegative).
 */
export function parseDecimalAR(
  raw: string,
  options: { allowNegative?: boolean } = {},
): string | null {
  let input = raw.trim().replace(/\$/g, "").replace(/\s+/g, "");
  if (input === "") return null;

  let negative = false;
  if (input.startsWith("-")) {
    if (!options.allowNegative) return null;
    negative = true;
    input = input.slice(1);
  }
  if (!/^[\d.,]+$/.test(input) || !/\d/.test(input)) return null;

  const lastDot = input.lastIndexOf(".");
  const lastComma = input.lastIndexOf(",");
  let intPart: string;
  let fracPart = "";

  if (lastDot >= 0 && lastComma >= 0) {
    const decimalSep = lastDot > lastComma ? "." : ",";
    const thousandsSep = decimalSep === "." ? "," : ".";
    const [whole, frac, ...rest] = input.split(decimalSep);
    if (rest.length > 0 || frac === undefined || frac.includes(thousandsSep)) return null;
    if (!validThousands(whole, thousandsSep)) return null;
    intPart = whole.split(thousandsSep).join("");
    fracPart = frac;
  } else if (lastComma >= 0) {
    const parts = input.split(",");
    if (parts.length === 2) {
      [intPart, fracPart] = parts;
    } else if (validThousands(input, ",")) {
      intPart = parts.join("");
    } else {
      return null;
    }
  } else if (lastDot >= 0) {
    const parts = input.split(".");
    if (parts.length > 2) {
      if (!validThousands(input, ".")) return null;
      intPart = parts.join("");
    } else if (parts[1].length === 3 && parts[0].length > 0 && parts[0] !== "0") {
      intPart = parts.join(""); // "1.500" → mil quinientos
    } else {
      [intPart, fracPart] = parts;
    }
  } else {
    intPart = input;
  }

  if (intPart === "") intPart = "0";
  if (!/^\d+$/.test(intPart) || (fracPart !== "" && !/^\d+$/.test(fracPart))) return null;
  intPart = intPart.replace(/^0+(?=\d)/, "");
  fracPart = fracPart.replace(/0+$/, "");
  const value = fracPart ? `${intPart}.${fracPart}` : intPart;
  return negative && value !== "0" ? `-${value}` : value;
}

function validThousands(value: string, sep: string): boolean {
  const groups = value.split(sep);
  if (groups.length === 1) return /^\d+$/.test(value);
  return (
    /^\d{1,3}$/.test(groups[0]) && groups.slice(1).every((group) => /^\d{3}$/.test(group))
  );
}
