import { describe, expect, it } from "vitest";

import type { EventDetail, Schemas } from "@/lib/api/types";

import { messageKind, supplierMessage, whatsappLink, whatsappNumber } from "./supplier-message";

describe("whatsappNumber", () => {
  it.each([
    ["+54 9 11 5555-0000", "5491155550000"],
    ["+54 11 5555-0000", "5491155550000"], // falta el 9 de celular
    ["0054 9 11 5555 0000", "5491155550000"],
    ["11 5555-0000", "5491155550000"],
    ["011 15 5555-0000", "5491155550000"],
    ["0351 15 512-3456", "5493515123456"],
    ["2944 15 12 3456", "5492944123456"],
    ["549 11 5555 0000", "5491155550000"],
    ["+34 600 123 456", "34600123456"], // otro país: tal cual
  ])("%s → %s", (raw, expected) => {
    expect(whatsappNumber(raw)).toBe(expected);
  });

  it.each([null, "", "interno 23", "5555-0000"])("%s no se puede interpretar → null", (raw) => {
    expect(whatsappNumber(raw)).toBeNull();
  });
});

const supplier = (over: Partial<Schemas["EventSupplierOut"]> = {}): Schemas["EventSupplierOut"] => ({
  id: "s1",
  supplier_id: "p1",
  supplier_name: "Sonido Sur",
  contact_name: "Lucía Gómez",
  contact_phone: "11 5555-0000",
  status: "TO_HIRE",
  budgeted_cost: null,
  items: [{ line_key: "l1", name: "Sonido", quantity: "1", unit_code: "u", days: 1, cost_total: null }],
  notes: null,
  invoice_number: null,
  payment_terms: null,
  confirmed_at: null,
  paid_at: null,
  ...over,
});

const event = { name: "Fiesta Nike", start_date: "2026-12-10", venue: "La Rural", city: "CABA" } as EventDetail;

describe("messageKind", () => {
  it("sigue el estado del proveedor y, si está confirmado, si el evento ya pasó", () => {
    expect(messageKind(supplier(), event, "2026-12-01")).toBe("confirm");
    expect(messageKind(supplier({ status: "CONFIRMED" }), event, "2026-12-01")).toBe("reminder");
    expect(messageKind(supplier({ status: "CONFIRMED" }), event, "2026-12-10")).toBe("invoice");
    expect(messageKind(supplier({ status: "INVOICED" }), event, "2026-12-20")).toBe("transfer");
    expect(messageKind(supplier({ status: "PAID" }), event, "2026-12-30")).toBe("paid");
    expect(messageKind(supplier({ status: "CANCELLED" }), event, "2026-12-01")).toBeNull();
  });
});

describe("supplierMessage", () => {
  it("pide confirmación con el evento, la fecha, el lugar y los ítems", () => {
    expect(supplierMessage("confirm", supplier(), event, "Productora X")).toBe(
      "Hola Lucía! Te escribo de Productora X por Fiesta Nike el 10/12/2026 en La Rural, CABA. ¿Me confirmás Sonido? Gracias!",
    );
  });

  it("pide el CBU nombrando la factura", () => {
    const text = supplierMessage("transfer", supplier({ status: "INVOICED", invoice_number: "A-0001-123" }), event, "X");
    expect(text).toBe("Hola Lucía! Tenemos tu factura A-0001-123 de Fiesta Nike. ¿Me confirmás el CBU o alias para transferirte? Gracias!");
  });

  it("sin contacto ni fecha, el mensaje igual se entiende", () => {
    const text = supplierMessage("reminder", supplier({ contact_name: null }), { ...event, start_date: null, venue: null }, "X");
    expect(text).toBe("Hola! Te recuerdo Fiesta Nike: Sonido. Cualquier cosa avisame. Gracias!");
  });

  it("resume listas largas de ítems", () => {
    const items = ["A", "B", "C", "D", "E"].map((name, i) => ({ ...supplier().items[0], line_key: String(i), name }));
    expect(supplierMessage("invoice", supplier({ items }), event, "X")).toContain("por A, B, C y 2 ítems más de");
  });
});

describe("whatsappLink", () => {
  it("va al número del contacto, o sin número si no se puede interpretar", () => {
    expect(whatsappLink("Hola!", "11 5555-0000")).toBe("https://wa.me/5491155550000?text=Hola!");
    expect(whatsappLink("Hola y chau", null)).toBe("https://wa.me/?text=Hola%20y%20chau");
  });
});
