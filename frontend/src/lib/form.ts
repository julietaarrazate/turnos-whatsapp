/** Valor de texto de un formulario: recortado y `null` si quedó vacío (el backend distingue). */
export function textValue(form: FormData, name: string): string | null {
  const value = String(form.get(name) ?? "").trim();
  return value === "" ? null : value;
}
