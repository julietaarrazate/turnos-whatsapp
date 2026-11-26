"use client";

import { useMutation } from "@tanstack/react-query";
import { CheckCircle2, ExternalLink, FileText, MessageSquareWarning } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Notice } from "@/components/ui/notice";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import type { PublicApproval } from "@/lib/api/types";
import { formatDateTime } from "@/lib/format/date";

/** Lo que ve el cliente: el diseño y dos botones. Sin cuenta, desde el teléfono. */
export function PublicApprovalView({ data: initial, token }: { data: PublicApproval; token: string }) {
  const [data, setData] = useState(initial);
  const [name, setName] = useState("");
  const [changes, setChanges] = useState(false);
  const [comment, setComment] = useState("");
  const fileUrl = `/api/v1/public/approvals/${encodeURIComponent(token)}/file`;
  const decide = useMutation({
    mutationFn: async (decision: "APPROVED" | "CHANGES") =>
      unwrap(
        await api.POST("/api/v1/public/approvals/{token}/decision", {
          params: { path: { token } },
          body: { decision, name: name.trim(), comment: comment.trim() || null },
        }),
      ),
    onSuccess: setData,
  });
  const open = data.status === "PENDING";

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-xl flex-col gap-4 px-4 pt-6 pb-[calc(2rem+env(safe-area-inset-bottom))]">
      <header>
        <p className="text-sm font-semibold text-ink-muted">{data.organization_name}</p>
        <h1 className="text-2xl font-bold">{data.title}</h1>
        <p className="text-sm text-ink-muted">Diseño para {data.event_name}</p>
      </header>

      {data.kind === "IMAGE" ? (
        <a href={fileUrl} target="_blank" rel="noopener" className="block overflow-hidden rounded-2xl border border-line bg-subtle">
          {/* eslint-disable-next-line @next/next/no-img-element -- lo sirve la API con el token del link */}
          <img src={fileUrl} alt={data.title} className="w-full object-contain" />
        </a>
      ) : (
        <a
          href={data.kind === "LINK" ? (data.url ?? "#") : fileUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-3 rounded-2xl border border-line bg-surface p-4 font-semibold"
        >
          {data.kind === "LINK" ? <ExternalLink className="size-6 text-brand" aria-hidden /> : <FileText className="size-6 text-brand" aria-hidden />}
          {data.kind === "LINK" ? "Abrir el diseño" : "Abrir el PDF"}
        </a>
      )}

      {data.status === "APPROVED" ? (
        <Notice tone="success">
          <span className="flex items-center gap-2">
            <CheckCircle2 className="size-5" aria-hidden /> Aprobado por {data.decided_by_name}
            {data.decided_at ? ` el ${formatDateTime(data.decided_at)}` : ""}. ¡Gracias!
          </span>
        </Notice>
      ) : null}
      {data.status === "CHANGES" ? (
        <Notice tone="warning">
          Pediste cambios{data.decided_at ? ` el ${formatDateTime(data.decided_at)}` : ""}: “{data.comment}”. La productora te va a
          mandar la nueva versión.
        </Notice>
      ) : null}
      {data.status === "REPLACED" ? (
        <Notice tone="info">Hay una versión más nueva de este diseño: pedile el link nuevo a la productora.</Notice>
      ) : null}
      {data.status === "EXPIRED" ? <Notice tone="info">Este link venció: pedile uno nuevo a la productora.</Notice> : null}

      {open ? (
        <form
          aria-label="Tu respuesta"
          className="flex flex-col gap-3 rounded-2xl border border-line bg-surface p-4"
          onSubmit={(e) => {
            e.preventDefault();
            decide.mutate(changes ? "CHANGES" : "APPROVED");
          }}
        >
          <label className="flex flex-col gap-1.5 text-sm font-medium">
            Tu nombre
            <input
              value={name}
              onChange={(e) => setName(e.currentTarget.value)}
              required
              minLength={2}
              maxLength={120}
              autoComplete="name"
              placeholder="Ej.: Laura, de Natura"
              className="h-11 rounded-lg border border-line bg-surface px-3 text-base"
            />
          </label>
          {changes ? (
            <label className="flex flex-col gap-1.5 text-sm font-medium">
              ¿Qué cambios necesitás?
              <textarea
                value={comment}
                onChange={(e) => setComment(e.currentTarget.value)}
                required
                maxLength={1000}
                rows={3}
                placeholder="Ej.: el logo más grande y el fondo en blanco"
                className="rounded-lg border border-line bg-surface px-3 py-2 text-base"
              />
            </label>
          ) : null}
          {changes ? (
            <div className="flex flex-col gap-2 sm:flex-row">
              <Button type="submit" size="lg" loading={decide.isPending} disabled={name.trim().length < 2 || !comment.trim()}>
                <MessageSquareWarning className="size-5" aria-hidden /> Mandar los cambios
              </Button>
              <Button type="button" size="lg" variant="ghost" onClick={() => setChanges(false)}>
                Volver
              </Button>
            </div>
          ) : (
            <div className="flex flex-col gap-2 sm:flex-row">
              <Button type="submit" size="lg" loading={decide.isPending} disabled={name.trim().length < 2}>
                <CheckCircle2 className="size-5" aria-hidden /> Aprobado
              </Button>
              <Button type="button" size="lg" variant="secondary" onClick={() => setChanges(true)}>
                Pido cambios
              </Button>
            </div>
          )}
          {decide.isError ? <Notice tone="error">{errorMessage(decide.error)}</Notice> : null}
        </form>
      ) : null}
      <p className="mt-auto text-center text-xs text-ink-muted">Enviado con Handie</p>
    </main>
  );
}
