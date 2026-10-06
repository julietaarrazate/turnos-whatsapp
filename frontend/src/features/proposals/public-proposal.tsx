import { FileDown } from "lucide-react";

import type { PublicProposal } from "@/lib/api/types";
import { formatDateTime, formatDay } from "@/lib/format/date";
import { formatMoney } from "@/lib/format/number";

import { DecisionBox } from "./decision-box";

const STATUS_NOTICE: Partial<Record<PublicProposal["status"], string>> = {
  EXPIRED: "Esta propuesta venció. Pedí una actualización a la productora.",
  SUPERSEDED: "Hay una versión más reciente de esta propuesta. Pedile el link nuevo a la productora.",
};

function decisionNotice(decision: NonNullable<PublicProposal["decision"]>): string {
  const when = formatDateTime(decision.decided_at);
  if (decision.status === "REJECTED") return `Propuesta rechazada el ${when}.`;
  if (decision.method === "MANUAL") return `Propuesta aprobada el ${when}. ¡Gracias!`;
  const who = decision.decided_by_name ? ` por ${decision.decided_by_name}` : "";
  return `Propuesta aceptada${who} el ${when}. ¡Gracias!`;
}

function money(value: string | null | undefined, currency: string): string {
  return value ? formatMoney(value, currency) : "";
}

/** La propuesta tal como la ve el cliente. Solo usa campos del snapshot público. */
export function PublicProposalView({ data, token }: { data: PublicProposal; token: string }) {
  const p = data.proposal;
  const t = p.totals;
  const detailed = p.display_mode === "DETAILED";
  const notice = data.decision ? decisionNotice(data.decision) : STATUS_NOTICE[data.status];
  const includesIva = p.iva_display === "IVA_INCLUDED";
  return (
    <main className="mx-auto flex min-h-dvh max-w-2xl flex-col gap-6 px-4 py-8 sm:py-12">
      <header className="flex flex-col gap-1 border-b border-line pb-6">
        <p className="text-sm font-medium text-accent">{p.organization.name}</p>
        <h1 className="text-2xl font-semibold tracking-tight">{p.title}</h1>
        <p className="text-sm text-ink-muted">
          Propuesta #{p.proposal_number} para {p.client.name}
          {p.event.start_date ? ` · ${formatDay(p.event.start_date)}` : ""}
          {p.event.venue ? ` · ${p.event.venue}` : ""}
          {p.event.city ? ` · ${p.event.city}` : ""}
        </p>
        <p className="text-sm text-ink-muted">Válida hasta el {formatDay(p.valid_until)}</p>
        <a
          href={`/api/v1/public/proposals/${encodeURIComponent(token)}/pdf`}
          className="mt-2 inline-flex w-fit items-center gap-2 rounded-lg border border-line bg-surface px-3 py-1.5 text-sm font-medium"
        >
          <FileDown className="size-4" aria-hidden /> Descargar PDF
        </a>
      </header>

      {notice ? (
        <div role="status" className="rounded-lg border border-warning/30 bg-warning/10 px-4 py-3 text-sm">
          {notice}
        </div>
      ) : null}

      {p.sections.map((section, i) => (
        <section key={i} aria-label={section.title} className="flex flex-col gap-2">
          <div className="flex items-baseline justify-between gap-3">
            <h2 className="font-semibold">{section.title}</h2>
            {section.total ? <span className="font-medium tabular-nums">{money(section.total, p.currency)}</span> : null}
          </div>
          <ul className="divide-y divide-line rounded-xl border border-line bg-surface">
            {section.items.map((item, j) => (
              <li key={j} className="flex items-start gap-3 px-4 py-3 text-sm">
                <div className="min-w-0 flex-1">
                  <p className="whitespace-pre-line">{item.description}</p>
                  <p className="text-xs text-ink-muted">
                    {item.quantity} {item.unit}
                    {item.days ? ` × ${item.days} ${item.days === 1 ? "día" : "días"}` : ""}
                    {detailed && item.unit_price ? ` · ${money(item.unit_price, p.currency)} c/u` : ""}
                  </p>
                </div>
                {detailed && item.amount ? <span className="tabular-nums">{money(item.amount, p.currency)}</span> : null}
              </li>
            ))}
          </ul>
        </section>
      ))}

      <section aria-label="Total" className="rounded-xl border border-line bg-surface px-4 py-3 text-sm">
        {!includesIva ? (
          <>
            {t.global_discount ? (
              <>
                <div className="flex justify-between py-0.5">
                  <span>Subtotal</span>
                  <span className="tabular-nums">{money(t.subtotal, p.currency)}</span>
                </div>
                <div className="flex justify-between py-0.5">
                  <span>Descuento</span>
                  <span className="tabular-nums">−{money(t.global_discount, p.currency)}</span>
                </div>
              </>
            ) : null}
            <div className="flex justify-between py-0.5">
              <span>Neto</span>
              <span className="tabular-nums">{money(t.net, p.currency)}</span>
            </div>
            <div className="flex justify-between py-0.5">
              <span>IVA</span>
              <span className="tabular-nums">{money(t.iva, p.currency)}</span>
            </div>
          </>
        ) : null}
        <div className="mt-1 flex justify-between border-t border-line pt-2 text-base font-semibold">
          <span>Total{includesIva ? " (IVA incluido)" : ""}</span>
          <span className="tabular-nums">{money(t.total, p.currency)}</span>
        </div>
      </section>

      {p.payment_terms || p.terms ? (
        <section className="flex flex-col gap-3 text-sm">
          {p.payment_terms ? (
            <div>
              <h2 className="font-semibold">Forma de pago</h2>
              <p className="whitespace-pre-line text-ink-muted">{p.payment_terms}</p>
            </div>
          ) : null}
          {p.terms ? (
            <div>
              <h2 className="font-semibold">Condiciones</h2>
              <p className="whitespace-pre-line text-ink-muted">{p.terms}</p>
            </div>
          ) : null}
        </section>
      ) : null}

      {data.can_decide ? <DecisionBox token={token} contentHash={data.content_hash} total={money(t.total, p.currency)} /> : null}

      <footer className="mt-auto border-t border-line pt-4 text-xs text-ink-muted">
        {p.organization.legal_name ?? p.organization.name}
        {p.organization.tax_id ? ` · CUIT ${p.organization.tax_id}` : ""} · Presupuesto #{p.budget_number} v{p.version_no}
      </footer>
    </main>
  );
}
