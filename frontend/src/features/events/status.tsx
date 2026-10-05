import { cn } from "@/lib/cn";
import type { EventStatus } from "@/lib/api/types";

export const EVENT_STATUS_LABELS: Record<EventStatus, string> = {
  LEAD: "Consulta",
  QUOTING: "Presupuestando",
  SENT: "Enviado",
  NEGOTIATION: "En negociación",
  APPROVED: "Aprobado",
  IN_PRODUCTION: "En producción",
  COMPLETED: "Realizado",
  CLOSED: "Cerrado",
  LOST: "Perdido",
  CANCELLED: "Cancelado",
};

const TONES: Partial<Record<EventStatus, string>> = {
  APPROVED: "bg-success/10 text-success",
  IN_PRODUCTION: "bg-success/10 text-success",
  LOST: "bg-danger/10 text-danger",
  CANCELLED: "bg-danger/10 text-danger",
  SENT: "bg-accent/10 text-accent",
  NEGOTIATION: "bg-warning/15 text-warning",
};

export function EventStatusBadge({ status }: { status: EventStatus }) {
  return (
    <span className={cn("rounded px-1.5 py-0.5 text-xs whitespace-nowrap", TONES[status] ?? "bg-subtle text-ink-muted")}>
      {EVENT_STATUS_LABELS[status]}
    </span>
  );
}
