"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, Image as ImageIcon, Upload } from "lucide-react";
import { useState } from "react";

import { Notice } from "@/components/ui/notice";
import { useSession } from "@/features/auth/session";
import { ApiError, api, errorMessage, unwrap } from "@/lib/api/client";
import type { Schemas } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatDateTime } from "@/lib/format/date";
import { MAX_UPLOAD_BYTES, shrinkImage, toBase64, uploadName } from "@/lib/files";

type Plan = Schemas["PlanOut"];

const plansKey = (pieceId: string) => ["piece-plans", pieceId] as const;

export function planUrl(planId: string): string {
  return `/api/v1/piece-plans/${planId}/file`;
}

function PlanRow({ plan }: { plan: Plan }) {
  const Icon = plan.mime === "application/pdf" ? FileText : ImageIcon;
  return (
    <a
      href={planUrl(plan.id)}
      target="_blank"
      rel="noopener"
      className={cn(
        "flex min-h-12 items-center gap-3 rounded-xl px-3 py-2",
        plan.current ? "border border-line bg-surface" : "text-ink-muted hover:bg-subtle",
      )}
    >
      <Icon className={cn("size-5 shrink-0", plan.current ? "text-brand" : "")} aria-hidden />
      <span className="min-w-0 flex-1">
        <span className={cn("block truncate", plan.current && "font-semibold text-ink")}>{plan.title}</span>
        <span className="block truncate text-xs text-ink-muted">
          {plan.uploaded_by_name} · {formatDateTime(plan.created_at)}
        </span>
      </span>
      <span
        className={cn(
          "shrink-0 rounded-md px-2 py-0.5 text-xs font-bold",
          plan.current ? "bg-success/15 text-success" : "bg-subtle text-ink-muted",
        )}
      >
        v{plan.version}
        {plan.current ? " vigente" : ""}
      </span>
    </a>
  );
}

function UploadPlan({ pieceId, titles }: { pieceId: string; titles: string[] }) {
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("");
  const add = useMutation({
    mutationFn: async ({ file, title }: { file: File; title: string }) => {
      const blob = file.type.startsWith("image/") ? await shrinkImage(file) : file;
      if (blob.size > MAX_UPLOAD_BYTES) throw new ApiError(413, "upload_too_large", "El archivo pesa más de 10 MB");
      return unwrap(
        await api.POST("/api/v1/pieces/{piece_id}/plans", {
          params: { path: { piece_id: pieceId } },
          body: { title, filename: uploadName(file.name, blob), file_base64: await toBase64(blob) },
        }),
      );
    },
    onSuccess: () => {
      setTitle("");
      void queryClient.invalidateQueries({ queryKey: plansKey(pieceId) });
    },
  });
  const listId = `plan-titles-${pieceId}`;
  return (
    <div className="flex flex-col gap-2 rounded-xl border border-dashed border-line p-3">
      <label className="flex flex-col gap-1.5 text-sm font-medium">
        Título del plano
        <input
          value={title}
          onChange={(e) => setTitle(e.currentTarget.value)}
          maxLength={120}
          list={listId}
          placeholder="Ej.: Plano de corte y medidas"
          className="h-11 rounded-lg border border-line bg-surface px-3 text-base font-normal sm:text-sm"
        />
        <datalist id={listId}>
          {titles.map((t) => (
            <option key={t} value={t} />
          ))}
        </datalist>
      </label>
      <p className="text-xs text-ink-muted">Con un título que ya existe se sube como versión nueva y pasa a ser la vigente.</p>
      <label
        className={cn(
          "flex h-11 cursor-pointer items-center justify-center gap-2 rounded-lg bg-brand text-sm font-semibold text-white focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-ink",
          (!title.trim() || add.isPending) && "pointer-events-none opacity-50",
        )}
      >
        <Upload className="size-4" aria-hidden />
        {add.isPending ? "Subiendo…" : "Elegir archivo (PDF o imagen)"}
        <input
          type="file"
          accept="application/pdf,image/*"
          aria-label="Archivo del plano"
          className="sr-only"
          disabled={!title.trim() || add.isPending}
          onChange={(e) => {
            const file = e.currentTarget.files?.[0];
            e.currentTarget.value = "";
            if (file) add.mutate({ file, title: title.trim() });
          }}
        />
      </label>
      {add.isError ? <Notice tone="error">{errorMessage(add.error)}</Notice> : null}
    </div>
  );
}

/** "Planos y archivos" en la ficha: la versión vigente de cada título arriba, las viejas plegadas. */
export function PiecePlans({ pieceId, canUpload }: { pieceId: string; canUpload: boolean }) {
  const { me } = useSession();
  const plans = useQuery({
    queryKey: plansKey(pieceId),
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/pieces/{piece_id}/plans", { params: { path: { piece_id: pieceId } } })),
  });
  const current = plans.data?.filter((p) => p.current) ?? [];
  const old = plans.data?.filter((p) => !p.current) ?? [];
  return (
    <section aria-label="Planos y archivos" className="flex flex-col gap-2">
      <h3 className="font-semibold">Planos y archivos</h3>
      {plans.isError ? <Notice tone="error">{errorMessage(plans.error)}</Notice> : null}
      {plans.data && plans.data.length === 0 ? <p className="text-sm text-ink-muted">Todavía no hay planos.</p> : null}
      <div className="flex flex-col gap-1.5">
        {current.map((plan) => (
          <PlanRow key={plan.id} plan={plan} />
        ))}
      </div>
      {old.length ? (
        <details className="text-sm">
          <summary className="cursor-pointer py-1 text-ink-muted">Versiones anteriores ({old.length})</summary>
          <div className="mt-1 flex flex-col gap-1">
            {old.map((plan) => (
              <PlanRow key={plan.id} plan={plan} />
            ))}
          </div>
        </details>
      ) : null}
      {canUpload && me.uploads_enabled ? <UploadPlan pieceId={pieceId} titles={current.map((p) => p.title)} /> : null}
      {canUpload && !me.uploads_enabled ? (
        <p className="text-xs text-ink-muted">Los planos se suben cuando se configure el espacio de archivos.</p>
      ) : null}
    </section>
  );
}
