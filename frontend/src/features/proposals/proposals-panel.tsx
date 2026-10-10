"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, Copy, ExternalLink, FileDown, Send } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { SelectField, TextAreaField, TextField } from "@/components/ui/field";
import { Notice } from "@/components/ui/notice";
import { useSession } from "@/features/auth/session";
import { AttachmentField, AttachmentLink, type UploadedDocument, useUpload } from "@/features/documents/attachment";
import { budgetKey, EVENTS_KEY } from "@/features/budgets/keys";
import type { BudgetEditor } from "@/features/budgets/use-budget-editor";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import type { Budget, Proposal, Schemas } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatDateTime, formatDay } from "@/lib/format/date";
import { formatMoney } from "@/lib/format/number";
import { textValue } from "@/lib/form";

const proposalsKey = (budgetId: string) => ["proposals", budgetId] as const;

const STATUS: Record<Proposal["status"], { label: string; tone: string }> = {
  SENT: { label: "Enviada", tone: "bg-accent/10 text-accent" },
  VIEWED: { label: "Vista", tone: "bg-accent/10 text-accent" },
  ACCEPTED: { label: "Aceptada", tone: "bg-success/10 text-success" },
  REJECTED: { label: "Rechazada", tone: "bg-danger/10 text-danger" },
  EXPIRED: { label: "Vencida", tone: "bg-warning/15 text-warning" },
  SUPERSEDED: { label: "Reemplazada", tone: "bg-subtle text-ink-muted" },
  REVOKED: { label: "Anulada", tone: "bg-subtle text-ink-muted" },
};

function ShareBox({ path, budget, emailedTo }: { path: string; budget: Budget; emailedTo: string[] }) {
  const url = typeof window === "undefined" ? path : `${window.location.origin}${path}`;
  const [copied, setCopied] = useState(false);
  const message = `Hola! Te comparto la propuesta para ${budget.event.name}: ${url}`;
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-success/30 bg-success/10 p-4">
      <p className="text-sm font-medium">Propuesta lista. Compartí este link con el cliente:</p>
      {emailedTo.length ? <p className="text-sm">Se envió por email a {emailedTo.join(", ")}.</p> : null}
      <input readOnly value={url} aria-label="Link de la propuesta" onFocus={(e) => e.currentTarget.select()} className="h-10 w-full rounded-lg border border-line bg-surface px-3 text-sm" />
      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          onClick={() => {
            void navigator.clipboard?.writeText(url).then(() => setCopied(true));
          }}
        >
          <Copy className="size-4" aria-hidden /> {copied ? "¡Copiado!" : "Copiar link"}
        </Button>
        <a
          href={`https://wa.me/?text=${encodeURIComponent(message)}`}
          target="_blank"
          rel="noreferrer"
          className="inline-flex h-8 items-center gap-2 rounded-lg border border-line bg-surface px-3 text-sm font-medium"
        >
          <Send className="size-4" aria-hidden /> WhatsApp
        </a>
        <a href={url} target="_blank" rel="noreferrer" className="inline-flex h-8 items-center gap-2 px-3 text-sm text-accent">
          <ExternalLink className="size-4" aria-hidden /> Ver como el cliente
        </a>
      </div>
      <p className="text-xs text-ink-muted">
        Por seguridad, el link se muestra solo ahora. Si lo perdés, generá la propuesta de nuevo (la anterior queda reemplazada).
      </p>
    </div>
  );
}

type Sent = { path: string; emailedTo: string[] };

/** "a@x.com, b@y.com" o uno por línea → lista sin vacíos. */
function emailList(raw: string): string[] {
  return raw
    .split(/[\s,;]+/)
    .map((e) => e.trim())
    .filter(Boolean);
}

function SendDialog({ budget, editor, onSent }: { budget: Budget; editor: BudgetEditor; onSent: (sent: Sent | null) => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  useEffect(() => dialog.current?.showModal(), []);
  const draft = budget.version.status === "DRAFT";
  return (
    <dialog
      ref={dialog}
      aria-label="Generar propuesta"
      onClose={() => onSent(null)}
      className="m-auto w-[min(34rem,calc(100vw-2rem))] rounded-xl border border-line bg-surface p-0 shadow-2xl backdrop:bg-ink/30"
    >
      <form
        className="flex flex-col gap-4 p-5"
        onSubmit={(e) => {
          e.preventDefault();
          const form = new FormData(e.currentTarget);
          const body: Schemas["ProposalIn"] = {
            display_mode: String(form.get("display_mode")) as Schemas["ProposalIn"]["display_mode"],
            iva_display: String(form.get("iva_display")) as Schemas["ProposalIn"]["iva_display"],
            valid_days: Number(form.get("valid_days") || 7),
            payment_terms: textValue(form, "payment_terms"),
            terms: textValue(form, "terms"),
            email_to: emailList(String(form.get("email_to") ?? "")),
            email_message: textValue(form, "email_message"),
          };
          setSending(true);
          setError(null);
          let sent: Sent | null = null;
          void editor
            .run(async (lock) => {
              const created = unwrap(
                await api.POST("/api/v1/budgets/{budget_id}/proposals", {
                  params: { path: { budget_id: budget.id }, header: draft ? { "If-Match": lock } : {} },
                  body,
                }),
              );
              sent = { path: created.public_path, emailedTo: created.emailed_to };
              return unwrap(await api.GET("/api/v1/budgets/{budget_id}", { params: { path: { budget_id: budget.id } } }));
            })
            .then((result) => {
              setSending(false);
              if (result && sent) {
                onSent(sent);
                dialog.current?.close();
              } else {
                setError("No se pudo generar la propuesta. Revisá el presupuesto e intentá de nuevo.");
              }
            });
        }}
      >
        <h2 className="text-lg font-semibold">Generar propuesta</h2>
        {draft ? (
          <p className="text-sm text-ink-muted">
            Se guarda la versión {budget.version.version_no} (no se puede modificar después; para cambiar algo se crea otra versión).
          </p>
        ) : null}
        <SelectField
          label="Qué ve el cliente"
          name="display_mode"
          defaultValue="BY_SECTION"
          options={[
            { value: "BY_SECTION", label: "Totales por sección (sin precio por ítem)" },
            { value: "DETAILED", label: "Detalle con importe por ítem" },
            { value: "TOTAL_ONLY", label: "Solo el total" },
          ]}
        />
        <SelectField
          label="IVA"
          name="iva_display"
          defaultValue="PLUS_IVA"
          options={[
            { value: "PLUS_IVA", label: "Neto + IVA" },
            { value: "IVA_INCLUDED", label: "IVA incluido" },
          ]}
        />
        <TextField label="Vigencia (días)" name="valid_days" type="number" min={1} max={120} defaultValue={7} />
        <TextAreaField label="Forma de pago (opcional)" name="payment_terms" rows={2} maxLength={2000} placeholder="Ej.: 50 % al confirmar, saldo 7 días antes del evento" />
        <TextAreaField label="Condiciones (opcional)" name="terms" rows={3} maxLength={5000} />
        <TextField
          label="Enviar por email a (opcional)"
          name="email_to"
          type="text"
          inputMode="email"
          autoComplete="off"
          placeholder="cliente@empresa.com, otra@empresa.com"
          hint="Hasta 5 direcciones. Si te responden, el mail te llega a vos."
        />
        <TextAreaField label="Mensaje del email (opcional)" name="email_message" rows={2} maxLength={2000} />
        {error ? <Notice tone="error">{error}</Notice> : null}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={() => dialog.current?.close()}>
            Cancelar
          </Button>
          <Button type="submit" loading={sending}>
            Generar
          </Button>
        </div>
      </form>
    </dialog>
  );
}

function ApproveDialog({ proposal, onDone }: { proposal: Proposal; onDone: (approved: boolean) => void }) {
  const { me } = useSession();
  const [order, setOrder] = useState<UploadedDocument | null>(null);
  const upload = useUpload("purchase-orders", setOrder);
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => dialog.current?.showModal(), []);
  const approve = useMutation({
    mutationFn: async (body: Schemas["ApproveIn"]) =>
      unwrap(
        await api.POST("/api/v1/proposals/{proposal_id}/approve", {
          params: { path: { proposal_id: proposal.id } },
          body,
        }),
      ),
    onSuccess: () => {
      onDone(true);
      dialog.current?.close();
    },
  });
  return (
    <dialog
      ref={dialog}
      aria-label="Aprobar propuesta"
      onClose={() => onDone(false)}
      className="m-auto w-[min(30rem,calc(100vw-2rem))] rounded-xl border border-line bg-surface p-0 shadow-2xl backdrop:bg-ink/30"
    >
      <form
        className="flex flex-col gap-4 p-5"
        onSubmit={(e) => {
          e.preventDefault();
          const form = new FormData(e.currentTarget);
          approve.mutate({
            po_number: textValue(form, "po_number"),
            po_document_id: order?.id ?? null,
            comment: textValue(form, "comment"),
          });
        }}
      >
        <h2 className="text-lg font-semibold">Aprobar propuesta #{proposal.number}</h2>
        <p className="text-sm text-ink-muted">
          Para cuando el cliente confirma por otro medio (orden de compra, email, teléfono). La versión {proposal.version_no} pasa a
          ser la aprobada del evento: producción y el control de costos parten de ella.
        </p>
        <TextField label="N° de orden de compra (opcional)" name="po_number" maxLength={100} autoFocus />
        {me.uploads_enabled ? (
          <AttachmentField label="OC adjunta (opcional)" value={order} upload={upload} onRemove={() => setOrder(null)} />
        ) : null}
        <TextAreaField label="Comentario (opcional)" name="comment" rows={2} maxLength={2000} placeholder="Ej.: confirmó por mail el 3/10" />
        {approve.isError ? <Notice tone="error">{errorMessage(approve.error)}</Notice> : null}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={() => dialog.current?.close()}>
            Cancelar
          </Button>
          <Button type="submit" loading={approve.isPending} disabled={upload.isPending}>
            Aprobar
          </Button>
        </div>
      </form>
    </dialog>
  );
}

function decisionText(p: Proposal): string | null {
  if (!p.decided_at) return null;
  const when = formatDateTime(p.decided_at);
  if (p.status === "REJECTED") {
    const who = p.decided_by_name ?? "El cliente";
    return `${who} la rechazó ${when}${p.decision_comment ? `: “${p.decision_comment}”` : ""}`;
  }
  if (p.approval_method === "MANUAL") {
    return `Aprobada ${when}${p.po_number ? ` · OC ${p.po_number}` : ""}${p.decision_comment ? ` · ${p.decision_comment}` : ""}`;
  }
  const who = [p.decided_by_name, p.decided_by_email ? `(${p.decided_by_email})` : null].filter(Boolean).join(" ");
  return `Aceptada online por ${who} ${when}${p.decision_comment ? `: “${p.decision_comment}”` : ""}`;
}

const APPROVABLE: Proposal["status"][] = ["SENT", "VIEWED", "EXPIRED"];
const OPEN_EVENT = ["SENT", "NEGOTIATION"];

/** Generar propuesta, compartirla y ver el estado de las enviadas (P-01, P-05 a P-08). */
export function ProposalsPanel({ budget, editor }: { budget: Budget; editor: BudgetEditor }) {
  const { can } = useSession();
  const queryClient = useQueryClient();
  const [sending, setSending] = useState(false);
  const [shared, setShared] = useState<Sent | null>(null);
  const [approving, setApproving] = useState<Proposal | null>(null);
  const proposals = useQuery({
    queryKey: proposalsKey(budget.id),
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/budgets/{budget_id}/proposals", { params: { path: { budget_id: budget.id } } })),
  });
  const revoke = useMutation({
    mutationFn: async (id: string) =>
      unwrap(await api.POST("/api/v1/proposals/{proposal_id}/revoke", { params: { path: { proposal_id: id } } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: proposalsKey(budget.id) }),
  });
  const refreshAll = () => {
    void queryClient.invalidateQueries({ queryKey: proposalsKey(budget.id) });
    void queryClient.invalidateQueries({ queryKey: budgetKey(budget.id) });
    void queryClient.invalidateQueries({ queryKey: EVENTS_KEY });
  };
  const markLost = useMutation({
    mutationFn: async (reason: string) =>
      unwrap(
        await api.POST("/api/v1/events/{event_id}/status", {
          params: { path: { event_id: budget.event.id } },
          body: { to_status: "LOST", reason },
        }),
      ),
    onSuccess: () => refreshAll(),
  });
  const hasLines = budget.version.sections.some((s) => s.lines.length > 0);
  const latest = proposals.data?.[0];
  // §3.1: un rechazo no marca el evento como perdido; solo se sugiere.
  const suggestLost =
    latest?.status === "REJECTED" && OPEN_EVENT.includes(budget.event.status) && can("proposal.decide");

  return (
    <section aria-label="Propuestas" className="mb-4 rounded-xl border border-line bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-3">
        <h2 className="font-semibold">Propuestas al cliente</h2>
        {can("proposal.send") ? (
          <Button size="sm" disabled={!hasLines} onClick={() => setSending(true)}>
            <Send className="size-4" aria-hidden /> Generar propuesta
          </Button>
        ) : null}
      </div>
      <div className="flex flex-col gap-3 px-4 py-3">
        {shared ? <ShareBox path={shared.path} emailedTo={shared.emailedTo} budget={budget} /> : null}
        {revoke.isError ? <Notice tone="error">{errorMessage(revoke.error)}</Notice> : null}
        {markLost.isError ? <Notice tone="error">{errorMessage(markLost.error)}</Notice> : null}
        {suggestLost && latest ? (
          <div className="flex flex-wrap items-center gap-2 rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-sm">
            <span className="flex-1">El cliente rechazó la propuesta. Podés mandar otra versión o marcar el evento como perdido.</span>
            <Button
              size="sm"
              variant="secondary"
              loading={markLost.isPending}
              onClick={() =>
                markLost.mutate(`Rechazó la propuesta #${latest.number}${latest.decision_comment ? `: ${latest.decision_comment}` : ""}`)
              }
            >
              Marcar como perdido
            </Button>
          </div>
        ) : null}
        {proposals.data?.length ? (
          <ul className="divide-y divide-line">
            {proposals.data.map((p) => (
              <li key={p.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 text-sm">
                <span className={cn("rounded px-1.5 py-0.5 text-xs", STATUS[p.status].tone)}>{STATUS[p.status].label}</span>
                <span className="font-medium">
                  #{p.number} · v{p.version_no}
                </span>
                <span className="tabular-nums">{formatMoney(p.total, p.currency)}</span>
                <span className="text-ink-muted">
                  enviada {formatDateTime(p.sent_at)} · vence {formatDay(p.valid_until)}
                  {p.view_count ? ` · vista ${p.view_count} ${p.view_count === 1 ? "vez" : "veces"}` : " · sin abrir"}
                </span>
                <span className="ml-auto flex gap-1">
                  <a
                    href={`/api/v1/proposals/${p.id}/pdf`}
                    aria-label={`PDF de la propuesta #${p.number}`}
                    className="inline-flex h-8 items-center gap-1 rounded-lg px-2 text-sm text-accent hover:bg-subtle"
                  >
                    <FileDown className="size-4" aria-hidden /> PDF
                  </a>
                  {can("proposal.decide") && APPROVABLE.includes(p.status) ? (
                    <Button size="sm" variant="secondary" onClick={() => setApproving(p)}>
                      <BadgeCheck className="size-4" aria-hidden /> Aprobar
                    </Button>
                  ) : null}
                  {can("proposal.send") && (p.status === "SENT" || p.status === "VIEWED") ? (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-danger"
                      onClick={() => window.confirm("¿Anular esta propuesta? El link deja de funcionar.") && revoke.mutate(p.id)}
                    >
                      Anular
                    </Button>
                  ) : null}
                </span>
                {decisionText(p) ? (
                  <p className="basis-full text-ink-muted">
                    {decisionText(p)}
                    {p.po_document_id ? (
                      <>
                        {" · "}
                        <AttachmentLink href={`/api/v1/proposals/${p.id}/purchase-order`}>Ver OC</AttachmentLink>
                      </>
                    ) : null}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-ink-muted">Todavía no se envió ninguna.</p>
        )}
      </div>
      {approving ? (
        <ApproveDialog
          proposal={approving}
          onDone={(approved) => {
            setApproving(null);
            if (approved) refreshAll();
          }}
        />
      ) : null}
      {sending ? (
        <SendDialog
          budget={budget}
          editor={editor}
          onSent={(sent) => {
            setSending(false);
            if (sent) {
              setShared(sent);
              void queryClient.invalidateQueries({ queryKey: proposalsKey(budget.id) });
            }
          }}
        />
      ) : null}
    </section>
  );
}
