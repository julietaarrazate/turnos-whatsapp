"use client";

import { useInfiniteQuery } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { Notice } from "@/components/ui/notice";
import { PageHeader } from "@/components/ui/page-header";
import { ROLE_LABELS } from "@/features/auth/roles";
import { PIECE_STATUS } from "@/features/events/event-pieces";
import { EVENT_STATUS_LABELS } from "@/features/events/status";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import { formatDateTime } from "@/lib/format/date";

const ACTION_LABELS: Record<string, string> = {
  "org.settings_changed": "Cambió la configuración de la organización",
  "org.fiscal_changed": "Cambió los datos fiscales",
  "org.pricing_settings_changed": "Cambió la configuración de precios",
  "membership.invited": "Invitó a una persona",
  "membership.joined": "Se sumó a la organización",
  "membership.changed": "Cambió el rol de una persona",
  "membership.disabled": "Desactivó a una persona",
  "invitation.revoked": "Anuló una invitación",
  "budget.created": "Creó un presupuesto",
  "budget.duplicated": "Duplicó un presupuesto",
  "budget.imported": "Creó un presupuesto desde una planilla",
  "budget.exported": "Descargó el Excel de un presupuesto",
  "budget.version_created": "Abrió una nueva versión",
  "budget.version_frozen": "Guardó una versión del presupuesto",
  "budget.version_updated": "Cambió el cálculo del precio",
  "budget.draft_discarded": "Descartó un borrador",
  "budget.costs_refreshed": "Actualizó costos del presupuesto",
  "budget.rules_reapplied": "Volvió a aplicar los markups",
  "budget.line_added": "Agregó un ítem",
  "budget.line_updated": "Cambió un ítem",
  "budget.line_removed": "Quitó un ítem",
  "budget.package_added": "Agregó un paquete",
  "budget.section_removed": "Borró una sección",
  "proposal.sent": "Generó una propuesta",
  "proposal.viewed": "El cliente vio la propuesta",
  "proposal.accepted": "El cliente aceptó la propuesta",
  "proposal.rejected": "El cliente rechazó la propuesta",
  "proposal.approved": "Aprobó la propuesta a mano",
  "proposal.revoked": "Anuló una propuesta",
  "event.created": "Creó un evento",
  "event.updated": "Cambió los datos del evento",
  "event.status_changed": "Cambió el estado del evento",
  "event.baseline_changed": "Cambió la versión aprobada del evento",
  "production.started": "Inició la producción",
  "production.supplier_status": "Cambió el estado de un proveedor",
  "piece.created": "Agregó una pieza",
  "piece.status_changed": "Cambió la fase de una pieza",
  "piece.deleted": "Borró una pieza",
  "expense.created": "Cargó un gasto",
  "expense.updated": "Cambió un gasto",
  "expense.deleted": "Borró un gasto",
  "client.created": "Creó un cliente",
  "client.updated": "Cambió un cliente",
  "client.deleted": "Borró un cliente",
  "supplier.created": "Creó un proveedor",
  "supplier.updated": "Cambió un proveedor",
  "supplier.deleted": "Borró un proveedor",
  "product.created": "Creó un producto",
  "product.updated": "Cambió un producto",
  "product.deleted": "Borró un producto",
  "package.created": "Creó un paquete",
  "package.updated": "Cambió un paquete",
  "package.deleted": "Borró un paquete",
  "category.created": "Creó una categoría",
  "category.updated": "Cambió una categoría",
  "category.deleted": "Borró una categoría",
  "offer.created": "Agregó un proveedor a un producto",
  "offer.updated": "Cambió la oferta de un proveedor",
  "price.recorded": "Cargó un costo",
  "catalog.bulk_increase": "Aplicó un aumento masivo",
  "catalog.imported": "Importó el catálogo",
  "markup_rule.changed": "Cambió un markup por categoría",
  "sale_charge.changed": "Cambió un cargo sobre la venta",
  "fx_rate.recorded": "Cargó una cotización del dólar",
  "document.uploaded": "Subió un documento",
};

/** Nombres de los datos que se muestran; lo que no está acá (códigos internos) no se muestra. */
const FIELD_LABELS: Record<string, string> = {
  name: "Nombre",
  title: "Título",
  status: "Estado",
  reason: "Motivo",
  role: "Rol",
  email: "Email",
  number: "Nº",
  version_no: "Versión",
  piece: "Pieza",
  area: "Área",
  supplier: "Proveedor",
  description: "Descripción",
  amount: "Importe",
  note: "Nota",
  change_note: "Nota",
  po_number: "OC",
};

const VALUE_LABELS: Record<string, string> = {
  ...EVENT_STATUS_LABELS,
  ...ROLE_LABELS,
  ...Object.fromEntries(Object.entries(PIECE_STATUS).map(([k, v]) => [k, v.label])),
  TO_HIRE: "A contratar",
  CONFIRMED: "Confirmado",
  INVOICED: "Facturado",
  PAID: "Pagado",
};

function describeChange(value: Record<string, unknown> | null): string {
  if (!value) return "";
  return Object.entries(value)
    .filter(([key, v]) => FIELD_LABELS[key] && v !== null && v !== "" && typeof v !== "object")
    .map(([key, v]) => `${FIELD_LABELS[key]}: ${VALUE_LABELS[String(v)] ?? String(v)}`)
    .join(" · ");
}

export function AuditLog() {
  const logs = useInfiniteQuery({
    queryKey: ["audit-logs"],
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam }) =>
      unwrap(await api.GET("/api/v1/audit-logs", { params: { query: { before: pageParam, limit: 50 } } })),
    getNextPageParam: (page) => page.next_cursor ?? null,
  });

  return (
    <>
      <PageHeader title="Auditoría" description="Registro inalterable de los cambios importantes." />
      {logs.isError ? <Notice tone="error">{errorMessage(logs.error)}</Notice> : null}
      <section className="rounded-xl border border-line bg-surface px-5">
        <ul className="divide-y divide-line">
          {logs.data?.pages.flatMap((page) =>
            page.items.map((entry) => (
              <li key={entry.id} className="py-3 text-sm">
                <p className="font-medium">{ACTION_LABELS[entry.action] ?? "Otro cambio"}</p>
                <p className="break-words text-ink-muted">
                  {[formatDateTime(entry.created_at), describeChange(entry.after)].filter(Boolean).join(" · ")}
                </p>
              </li>
            )),
          )}
        </ul>
        {logs.data && logs.data.pages[0].items.length === 0 ? (
          <p className="py-4 text-sm text-ink-muted">Todavía no hay actividad registrada.</p>
        ) : null}
      </section>
      {logs.hasNextPage ? (
        <div className="mt-4 flex justify-center">
          <Button variant="secondary" loading={logs.isFetchingNextPage} onClick={() => logs.fetchNextPage()}>
            Ver más
          </Button>
        </div>
      ) : null}
    </>
  );
}
