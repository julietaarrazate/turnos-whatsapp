import { formatDay } from "@/lib/format/date";
import type { EventDetail, Schemas } from "@/lib/api/types";

type Supplier = Schemas["EventSupplierOut"];

/**
 * Número para wa.me (internacional, solo dígitos). Acepta como se suele cargar en Argentina:
 * "+54 9 11 5555-0000", "011 15 5555-0000", "351 155 123456"... Si no se puede interpretar con
 * seguridad devuelve null y WhatsApp se abre para elegir el contacto a mano.
 */
export function whatsappNumber(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const international = /^\s*(\+|00)/.test(raw);
  let digits = raw.replace(/\D/g, "");
  if (international) {
    digits = digits.replace(/^00/, "");
    // Celulares argentinos: WhatsApp los necesita con el 9 (54 9 …).
    if (digits.startsWith("54") && !digits.startsWith("549") && digits.length === 12) return `549${digits.slice(2)}`;
    return digits.length >= 8 ? digits : null;
  }
  if (digits.startsWith("549") && digits.length === 13) return digits;
  digits = digits.replace(/^0/, "");
  // Formato local con 15 (código de área de 2 a 4 dígitos + 15 + número): se saca el 15.
  if (digits.length === 12) {
    for (const area of [2, 3, 4]) {
      if (digits.slice(area, area + 2) === "15") {
        digits = digits.slice(0, area) + digits.slice(area + 2);
        break;
      }
    }
  }
  return digits.length === 10 ? `549${digits}` : null;
}

export type MessageKind = "confirm" | "reminder" | "invoice" | "transfer" | "paid";

export const MESSAGE_LABELS: Record<MessageKind, string> = {
  confirm: "Pedir confirmación",
  reminder: "Recordatorio",
  invoice: "Pedir factura",
  transfer: "Pedir CBU o alias",
  paid: "Avisar el pago",
};

/** Qué conviene mandarle según en qué está el proveedor (y si el evento ya pasó). */
export function messageKind(supplier: Supplier, event: EventDetail, today: string): MessageKind | null {
  switch (supplier.status) {
    case "TO_HIRE":
      return "confirm";
    case "CONFIRMED":
      return event.start_date && event.start_date <= today ? "invoice" : "reminder";
    case "INVOICED":
      return "transfer";
    case "PAID":
      return "paid";
    default:
      return null;
  }
}

function itemList(supplier: Supplier): string {
  const names = supplier.items.map((i) => i.name);
  if (names.length <= 4) return names.join(", ");
  return `${names.slice(0, 3).join(", ")} y ${names.length - 3} ítems más`;
}

function eventLine(event: EventDetail): string {
  const when = event.start_date ? ` el ${formatDay(event.start_date)}` : "";
  const where = event.venue ? ` en ${event.venue}${event.city ? `, ${event.city}` : ""}` : "";
  return `${event.name}${when}${where}`;
}

/** El texto armado para WhatsApp. `org` es quien firma (la productora). */
export function supplierMessage(kind: MessageKind, supplier: Supplier, event: EventDetail, org: string): string {
  const hello = supplier.contact_name ? `Hola ${supplier.contact_name.split(" ")[0]}!` : "Hola!";
  const items = itemList(supplier);
  const invoice = supplier.invoice_number ? ` ${supplier.invoice_number}` : "";
  const body = {
    confirm: `Te escribo de ${org} por ${eventLine(event)}. ¿Me confirmás ${items || "lo que cotizaste"}?`,
    reminder: `Te recuerdo ${eventLine(event)}${items ? `: ${items}` : ""}. Cualquier cosa avisame.`,
    invoice: `¿Me pasás la factura${items ? ` por ${items}` : ""} de ${event.name}?`,
    transfer: `Tenemos tu factura${invoice} de ${event.name}. ¿Me confirmás el CBU o alias para transferirte?`,
    paid: `Te aviso que ya transferimos el pago de la factura${invoice} de ${event.name}.`,
  }[kind];
  return `${hello} ${body} Gracias!`;
}

/** Link de WhatsApp: al número del contacto si se puede, si no para elegir el contacto. */
export function whatsappLink(text: string, phone: string | null | undefined): string {
  const number = whatsappNumber(phone);
  return `https://wa.me/${number ?? ""}?text=${encodeURIComponent(text)}`;
}
