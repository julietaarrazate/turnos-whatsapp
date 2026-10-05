"use client";

import { Check, X } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { TextAreaField, TextField } from "@/components/ui/field";
import { Notice } from "@/components/ui/notice";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import type { PublicProposal } from "@/lib/api/types";
import { textValue } from "@/lib/form";

type Mode = "idle" | "accept" | "reject";

/** Aceptar o rechazar desde el link (P-05). Manda el hash de lo que el cliente está viendo. */
export function DecisionBox({ token, contentHash, total }: { token: string; contentHash: string; total: string }) {
  const [mode, setMode] = useState<Mode>("idle");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PublicProposal | null>(null);

  if (result?.decision) {
    const accepted = result.decision.status === "ACCEPTED";
    return (
      <div role="status" className="rounded-xl border border-success/30 bg-success/10 px-4 py-4 text-sm">
        <p className="font-semibold">{accepted ? "¡Listo! Aceptaste la propuesta." : "Registramos tu respuesta."}</p>
        <p className="text-ink-muted">
          {accepted
            ? "La productora ya recibió el aviso y se va a comunicar con vos para los próximos pasos."
            : "Gracias por avisar. La productora ya recibió tu comentario."}
        </p>
      </div>
    );
  }

  const submit = (form: HTMLFormElement) => {
    const data = new FormData(form);
    setPending(true);
    setError(null);
    const path = { params: { path: { token } } };
    const request =
      mode === "accept"
        ? api.POST("/api/v1/public/proposals/{token}/accept", {
            ...path,
            body: {
              content_hash: contentHash,
              name: String(data.get("name")).trim(),
              email: String(data.get("email")).trim(),
              comment: textValue(data, "comment"),
            },
          })
        : api.POST("/api/v1/public/proposals/{token}/reject", {
            ...path,
            body: {
              content_hash: contentHash,
              reason: String(data.get("reason")).trim(),
              name: textValue(data, "name"),
              email: textValue(data, "email"),
            },
          });
    void request
      .then((response) => setResult(unwrap(response)))
      .catch((err: unknown) => setError(errorMessage(err)))
      .finally(() => setPending(false));
  };

  if (mode === "idle") {
    return (
      <section aria-label="Respuesta" className="flex flex-col gap-2 rounded-xl border border-line bg-surface p-4">
        <p className="text-sm text-ink-muted">¿Te sirve la propuesta? Respondé desde acá.</p>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Button size="lg" className="flex-1" onClick={() => setMode("accept")}>
            <Check className="size-5" aria-hidden /> Aceptar propuesta
          </Button>
          <Button size="lg" variant="secondary" className="flex-1" onClick={() => setMode("reject")}>
            <X className="size-5" aria-hidden /> No me sirve
          </Button>
        </div>
      </section>
    );
  }

  const accepting = mode === "accept";
  return (
    <form
      aria-label={accepting ? "Aceptar propuesta" : "Rechazar propuesta"}
      className="flex flex-col gap-4 rounded-xl border border-line bg-surface p-4"
      onSubmit={(e) => {
        e.preventDefault();
        submit(e.currentTarget);
      }}
    >
      <h2 className="font-semibold">
        {accepting ? (
          <>
            Aceptar la propuesta por <span className="whitespace-nowrap">{total}</span>
          </>
        ) : (
          "Contanos qué no te sirvió"
        )}
      </h2>
      {accepting ? (
        <>
          <TextField label="Tu nombre" name="name" required maxLength={200} autoComplete="name" />
          <TextField label="Tu email" name="email" type="email" required maxLength={320} autoComplete="email" />
          <TextAreaField label="Comentario (opcional)" name="comment" rows={2} maxLength={2000} />
          <p className="text-xs text-ink-muted">
            Al aceptar quedan registrados tu nombre, tu email, la fecha y esta versión exacta de la propuesta.
          </p>
        </>
      ) : (
        <>
          <TextAreaField label="Motivo" name="reason" required rows={3} maxLength={2000} placeholder="Ej.: se pasa de nuestro presupuesto, cambió la fecha…" />
          <TextField label="Tu nombre (opcional)" name="name" maxLength={200} autoComplete="name" />
          <TextField label="Tu email (opcional)" name="email" type="email" maxLength={320} autoComplete="email" />
        </>
      )}
      {error ? <Notice tone="error">{error}</Notice> : null}
      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <Button type="button" variant="ghost" onClick={() => setMode("idle")}>
          Volver
        </Button>
        <Button type="submit" size="lg" variant={accepting ? "primary" : "danger"} loading={pending}>
          {accepting ? "Confirmar aceptación" : "Enviar respuesta"}
        </Button>
      </div>
    </form>
  );
}
