"use client";

import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Camera, CheckCircle2, FileText, Hammer, PlusCircle, Truck } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Notice } from "@/components/ui/notice";
import { PIECE_STATUS } from "@/features/events/event-pieces";
import { audioUrl, photoUrl } from "@/features/pieces/piece-progress";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import type { Schemas } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { LIVE } from "@/lib/live";

import { UNREAD_KEY, useUnread } from "./bell";

type Item = Schemas["ActivityOut"];
type PieceStatus = Schemas["PieceStatus"];

const SUPPLIER_STATUS: Record<string, string> = {
  TO_HIRE: "a contratar",
  CONFIRMED: "confirmado",
  INVOICED: "facturado",
  PAID: "pagado",
  CANCELLED: "cancelado",
};

/** "hace 5 min", "hace 3 h", "ayer", "lun 24/11". */
export function timeAgo(iso: string, now: Date = new Date()): string {
  const then = new Date(iso);
  const minutes = Math.round((now.getTime() - then.getTime()) / 60_000);
  if (minutes < 1) return "recién";
  if (minutes < 60) return `hace ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `hace ${hours} h`;
  if (hours < 48) return "ayer";
  return new Intl.DateTimeFormat("es-AR", {
    weekday: "short",
    day: "2-digit",
    month: "2-digit",
    timeZone: "America/Argentina/Buenos_Aires",
  }).format(then);
}

/** Llegó después de la última vez que se miró (si nunca se miró, nada se marca como nuevo). */
export function isNewSince(createdAt: string, since: string | null | undefined): boolean {
  return Boolean(since) && Date.parse(createdAt) > Date.parse(since!);
}

/** La frase de cada movimiento, en castellano y sin códigos. */
export function describe(item: Item): string {
  const piece = item.piece ?? "una pieza";
  switch (item.kind) {
    case "piece.status_changed": {
      const status = item.status && item.status in PIECE_STATUS ? PIECE_STATUS[item.status as PieceStatus].label : item.status;
      return `pasó ${piece} a ${status ?? "otra fase"}`;
    }
    case "piece.update_posted":
      if (item.has_photo) return `subió una foto de avance de ${piece}`;
      return item.has_audio ? `dejó una nota de voz en ${piece}` : `dejó una nota en ${piece}`;
    case "piece.plan_uploaded":
      return `subió ${item.title ?? "un plano"}${item.version ? ` v${item.version}` : ""} de ${piece}`;
    case "piece.created":
      return `agregó la pieza ${piece}`;
    case "production.started":
      return "inició la producción";
    case "production.supplier_status":
      return `marcó ${item.supplier ?? "un proveedor"} como ${SUPPLIER_STATUS[item.status ?? ""] ?? "otro estado"}`;
    default:
      return "hizo un cambio";
  }
}

const ICONS: Record<string, typeof Camera> = {
  "piece.status_changed": Hammer,
  "piece.update_posted": Camera,
  "piece.plan_uploaded": FileText,
  "piece.created": PlusCircle,
  "production.started": CheckCircle2,
  "production.supplier_status": Truck,
};

function ActivityItem({ item, isNew }: { item: Item; isNew: boolean }) {
  const Icon = ICONS[item.kind] ?? Hammer;
  const mounted = item.kind === "piece.status_changed" && item.status === "MOUNTED";
  return (
    <li className="flex gap-3 py-3">
      <span
        className={cn(
          "flex size-10 shrink-0 items-center justify-center rounded-full",
          item.kind === "piece.update_posted" ? "bg-magenta/10 text-magenta" : mounted ? "bg-fill text-white" : "bg-brand/10 text-brand",
        )}
      >
        <Icon className="size-5" aria-hidden />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-sm">
          {isNew ? <span className="mr-1.5 rounded bg-magenta px-1.5 py-0.5 text-[10px] font-bold text-white uppercase">Nuevo</span> : null}
          <strong>{item.actor_name ?? "Alguien"}</strong> {describe(item)}
        </p>
        <p className="text-xs text-ink-muted">
          <Link href={`/events/${item.event.id}/pieces`} className="hover:underline">
            #{item.event.number} {item.event.name}
          </Link>{" "}
          · {timeAgo(item.created_at)}
        </p>
        {item.note ? <p className="mt-1 text-sm text-ink">“{item.note}”</p> : null}
        {item.has_audio && item.update_id ? (
          <audio
            src={audioUrl(item.update_id)}
            controls
            preload="none"
            className="mt-2 h-10 w-full max-w-xs"
            aria-label={`Nota de voz de ${item.actor_name ?? "alguien"}`}
          />
        ) : null}
        {item.has_photo && item.update_id ? (
          <a href={photoUrl(item.update_id)} target="_blank" rel="noopener" className="mt-2 block w-40 overflow-hidden rounded-xl bg-subtle">
            {/* eslint-disable-next-line @next/next/no-img-element -- la API sirve la foto con permiso de sesión */}
            <img src={photoUrl(item.update_id)} alt={`Foto de avance de ${item.piece ?? "la pieza"}`} loading="lazy" className="aspect-[4/3] w-full object-cover" />
          </a>
        ) : null}
      </div>
    </li>
  );
}

/** "Actividad": lo que pasa en producción, lo más nuevo arriba. */
export function ActivityFeed() {
  const feed = useInfiniteQuery({
    queryKey: ["activity"],
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam }) =>
      unwrap(await api.GET("/api/v1/activity", { params: { query: { before: pageParam ?? undefined } } })),
    getNextPageParam: (page) => page.next_before ?? null,
    ...LIVE,
  });
  const items = feed.data?.pages.flatMap((page) => page.items) ?? [];
  // Lo nuevo se marca contra lo que se había visto al entrar; después se apaga la campanita.
  const queryClient = useQueryClient();
  const unread = useUnread();
  const [since, setSince] = useState<string | null | undefined>(undefined);
  const seen = useMutation({
    mutationFn: async () => unwrap(await api.POST("/api/v1/activity/seen", { body: {} })),
    onSuccess: (data) => queryClient.setQueryData(UNREAD_KEY, data),
  });
  const { mutate: markSeen } = seen;
  const ready = unread.isSuccess && since === undefined;
  const previous = unread.data?.seen_at ?? null;
  useEffect(() => {
    if (!ready) return;
    setSince(previous); // eslint-disable-line react-hooks/set-state-in-effect -- se fija una sola vez, al entrar
    markSeen();
  }, [ready, previous, markSeen]);
  // Mientras se está mirando, lo que llega también queda visto.
  const newest = items[0]?.id;
  useEffect(() => {
    if (since !== undefined && newest) markSeen();
  }, [since, newest, markSeen]);
  return (
    <div className="flex flex-col gap-4">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">Actividad</h1>
        <p className="mt-1 text-sm text-ink-muted">Lo que pasa en el taller y en los montajes, lo más nuevo arriba.</p>
      </header>
      {feed.isPending ? <p className="text-sm text-ink-muted">Cargando…</p> : null}
      {feed.isError ? <Notice tone="error">{errorMessage(feed.error)}</Notice> : null}
      {feed.data && items.length === 0 ? (
        <p className="rounded-xl border border-line bg-surface p-6 text-sm text-ink-muted">
          Todavía no hay movimientos. Cuando alguien cambie la fase de una pieza o suba una foto, aparece acá.
        </p>
      ) : null}
      {items.length ? (
        <section aria-label="Movimientos" className="rounded-xl border border-line bg-surface px-4">
          <ul className="divide-y divide-line">
            {items.map((item) => (
              <ActivityItem key={item.id} item={item} isNew={isNewSince(item.created_at, since)} />
            ))}
          </ul>
        </section>
      ) : null}
      {feed.hasNextPage ? (
        <div className="flex justify-center">
          <Button variant="secondary" loading={feed.isFetchingNextPage} onClick={() => feed.fetchNextPage()}>
            Ver anteriores
          </Button>
        </div>
      ) : null}
    </div>
  );
}
