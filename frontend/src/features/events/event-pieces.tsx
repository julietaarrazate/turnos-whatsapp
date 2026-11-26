"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ChevronRight, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Notice } from "@/components/ui/notice";
import { useSession } from "@/features/auth/session";
import { EVENTS_KEY } from "@/features/budgets/keys";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import type { Schemas } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatDay } from "@/lib/format/date";

type Piece = Schemas["PieceOut"];
type PieceStatus = Schemas["PieceStatus"];
type PieceArea = Schemas["PieceArea"];

export const piecesKey = (eventId: string) => [...EVENTS_KEY, "pieces", eventId] as const;

/** Fases de una pieza, en orden. Colores con distinta claridad: se distinguen sin depender del tono. */
export const PIECE_STATUS: Record<PieceStatus, { label: string; short: string; tone: string }> = {
  DESIGN: { label: "Pendiente diseño", short: "Pend. diseño", tone: "bg-[#E4E4EE] text-[#3A3D5C]" },
  TO_BUY: { label: "Aprobado / a comprar", short: "A comprar", tone: "bg-[#FFE08A] text-[#5A3B00]" },
  IN_WORKSHOP: { label: "En taller", short: "En taller", tone: "bg-[#FFB27A] text-[#5A1F00]" },
  READY: { label: "Listo para carga", short: "Listo carga", tone: "bg-[#A9DBFF] text-[#003A5C]" },
  MOUNTED: { label: "En predio / montado", short: "Montado", tone: "bg-[#2B2FA8] text-white" },
};
const PHASES = Object.keys(PIECE_STATUS) as PieceStatus[];

export const PIECE_AREA: Record<PieceArea, string> = {
  CARPENTRY: "Carpintería",
  METAL: "Herrería",
  GRAPHICS: "Gráfica y corpóreos",
  OTHER: "Otros",
};
const AREAS = Object.keys(PIECE_AREA) as PieceArea[];

function usePieces(eventId: string) {
  return useQuery({
    queryKey: piecesKey(eventId),
    queryFn: async () => unwrap(await api.GET("/api/v1/events/{event_id}/pieces", { params: { path: { event_id: eventId } } })),
  });
}

function useUpdatePiece(eventId: string, pieceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: Schemas["PieceUpdate"]) =>
      unwrap(await api.PATCH("/api/v1/pieces/{piece_id}", { params: { path: { piece_id: pieceId } }, body })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: piecesKey(eventId) }),
  });
}

export function StatusChip({ status, className }: { status: PieceStatus; className?: string }) {
  return (
    <span className={cn("shrink-0 rounded-md px-2 py-1 text-xs font-bold", PIECE_STATUS[status].tone, className)}>
      {PIECE_STATUS[status].short}
    </span>
  );
}

function pieceMeta(piece: Piece): string {
  const who = piece.assignee_name ?? "Sin responsable";
  if (!piece.due_date) return who;
  return `${who} · ${piece.late ? "vencía" : "vence"} ${formatDay(piece.due_date)}`;
}

function AddPiece({ eventId }: { eventId: string }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [area, setArea] = useState<PieceArea>("CARPENTRY");
  const add = useMutation({
    mutationFn: async (body: Schemas["PieceIn"]) =>
      unwrap(await api.POST("/api/v1/events/{event_id}/pieces", { params: { path: { event_id: eventId } }, body })),
    onSuccess: (_, sent) => {
      // Solo se limpia si no se empezó a escribir la siguiente mientras se guardaba.
      setName((current) => (current.trim() === sent.name ? "" : current));
      void queryClient.invalidateQueries({ queryKey: piecesKey(eventId) });
    },
  });
  return (
    <form
      aria-label="Agregar pieza"
      className="flex flex-wrap gap-2 rounded-xl border border-line bg-surface p-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (name.trim()) add.mutate({ name: name.trim(), area });
      }}
    >
      <input
        value={name}
        onChange={(e) => setName(e.currentTarget.value)}
        maxLength={200}
        aria-label="Nombre de la pieza"
        placeholder="Nueva pieza: ej. Mostrador recepción"
        className="h-11 min-w-0 flex-[999_1_14rem] rounded-lg border border-line bg-surface px-3 text-base sm:text-sm"
      />
      <select
        value={area}
        onChange={(e) => setArea(e.currentTarget.value as PieceArea)}
        aria-label="Área"
        className="h-11 flex-1 rounded-lg border border-line bg-surface px-2 text-base sm:text-sm"
      >
        {AREAS.map((a) => (
          <option key={a} value={a}>
            {PIECE_AREA[a]}
          </option>
        ))}
      </select>
      <Button type="submit" size="lg" loading={add.isPending} className="flex-1">
        <Plus className="size-4" aria-hidden /> Agregar
      </Button>
      {add.isError ? <Notice tone="error">{errorMessage(add.error)}</Notice> : null}
    </form>
  );
}

/** Pestaña Piezas: el tablero de fabricación del evento, agrupado por área. */
export function EventPieces({ id }: { id: string }) {
  const { can } = useSession();
  const pieces = usePieces(id);
  const [area, setArea] = useState<PieceArea | null>(null);

  if (pieces.isPending) return <p className="text-sm text-ink-muted">Cargando…</p>;
  if (pieces.isError) return <Notice tone="error">{errorMessage(pieces.error)}</Notice>;
  const data = pieces.data;
  const visible = AREAS.filter((a) => !area || a === area)
    .map((a) => ({ area: a, items: data.pieces.filter((p) => p.area === a) }))
    .filter((g) => g.items.length > 0);
  const late = data.pieces.filter((p) => p.late).length;

  return (
    <div className="flex flex-col gap-4">
      <section aria-label="Avance de las piezas" className="flex flex-col gap-2 rounded-xl border border-line bg-surface p-4">
        <div className="flex items-baseline justify-between gap-2">
          <h2 className="font-semibold">Avance</h2>
          <span className="text-sm text-ink-muted">
            {data.ready} de {data.total} listas
            {late ? <strong className="text-danger"> · {late === 1 ? "1 atrasada" : `${late} atrasadas`}</strong> : null}
          </span>
        </div>
        <div className="flex items-center gap-3">
          <div className="h-2 flex-1 overflow-hidden rounded bg-subtle">
            <div className="h-2 rounded bg-accent" style={{ width: `${data.progress}%` }} />
          </div>
          <span className="text-sm font-bold tabular-nums">{data.progress}%</span>
        </div>
      </section>

      <div role="group" aria-label="Filtrar por área" className="flex flex-wrap gap-2">
        {[null, ...AREAS].map((a) => (
          <button
            key={a ?? "all"}
            type="button"
            aria-pressed={area === a}
            onClick={() => setArea(a)}
            className={cn(
              "h-9 rounded-full px-4 text-sm font-semibold",
              area === a ? "bg-ink text-surface" : "border border-line bg-surface text-ink",
            )}
          >
            {a ? PIECE_AREA[a] : `Todas · ${data.total}`}
          </button>
        ))}
      </div>

      {can("production.manage") ? <AddPiece eventId={id} /> : null}

      {visible.length === 0 ? (
        <Notice tone="info">
          {data.total ? "No hay piezas en esta área." : "Todavía no hay piezas. Cargá lo que se fabrica para este evento: mostradores, corpóreos, tarimas…"}
        </Notice>
      ) : null}

      {visible.map((group) => (
        <section key={group.area} aria-label={PIECE_AREA[group.area]} className="flex flex-col gap-2">
          <h2 className="text-sm font-bold">
            {PIECE_AREA[group.area]} <span className="font-normal text-ink-muted">· {group.items.length}</span>
          </h2>
          <ul className="flex flex-col gap-2">
            {group.items.map((piece) => (
              <li key={piece.id}>
                <Link
                  href={`/events/${id}/pieces/${piece.id}`}
                  className={cn(
                    "flex min-h-14 items-center gap-3 rounded-xl border bg-surface px-3 py-2.5 hover:bg-subtle",
                    piece.late ? "border-danger" : "border-line",
                  )}
                >
                  <span className="flex min-w-0 flex-1 flex-col">
                    <span className="truncate font-semibold">{piece.name}</span>
                    <span className={cn("text-sm", piece.late ? "font-bold text-danger" : "text-ink-muted")}>{pieceMeta(piece)}</span>
                  </span>
                  <StatusChip status={piece.status} />
                  <ChevronRight className="size-4 shrink-0 text-ink-muted" aria-hidden />
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

/** Ficha de una pieza: las fases como botones grandes de un toque, responsable, fecha y notas. */
export function PieceDetail({ eventId, pieceId }: { eventId: string; pieceId: string }) {
  const { can } = useSession();
  const router = useRouter();
  const queryClient = useQueryClient();
  const pieces = usePieces(eventId);
  const update = useUpdatePiece(eventId, pieceId);
  const editable = can("production.manage");
  const members = useQuery({
    queryKey: ["members", "active"],
    queryFn: async () => unwrap(await api.GET("/api/v1/members")),
    enabled: editable,
  });
  const remove = useMutation({
    mutationFn: async () => unwrap(await api.DELETE("/api/v1/pieces/{piece_id}", { params: { path: { piece_id: pieceId } } })),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: piecesKey(eventId) });
      router.push(`/events/${eventId}/pieces`);
    },
  });

  if (pieces.isPending) return <p className="text-sm text-ink-muted">Cargando…</p>;
  if (pieces.isError) return <Notice tone="error">{errorMessage(pieces.error)}</Notice>;
  const piece = pieces.data.pieces.find((p) => p.id === pieceId);
  if (!piece) return <Notice tone="error">La pieza no existe o fue borrada.</Notice>;
  const active = (members.data ?? []).filter((m) => m.status === "ACTIVE");
  // Optimista: el botón tocado se marca al instante.
  const current = update.isPending && update.variables?.status ? update.variables.status : piece.status;

  return (
    <div className="flex flex-col gap-5">
      <Link href={`/events/${eventId}/pieces`} className="inline-flex items-center gap-1 text-sm text-ink-muted hover:text-ink">
        <ArrowLeft className="size-4" aria-hidden /> Piezas
      </Link>
      <header>
        <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">{PIECE_AREA[piece.area]}</p>
        <h2 className="text-2xl font-bold tracking-tight">{piece.name}</h2>
        <p className={cn("mt-1 text-sm", piece.late ? "font-bold text-danger" : "text-ink-muted")}>{pieceMeta(piece)}</p>
      </header>

      <section aria-label="Estado de la pieza" className="flex flex-col gap-2">
        <h3 className="font-semibold">Estado</h3>
        <div className="grid grid-cols-5 gap-1.5">
          {PHASES.map((phase) => {
            const on = phase === current;
            return (
              <button
                key={phase}
                type="button"
                aria-pressed={on}
                disabled={!editable || update.isPending}
                onClick={() => update.mutate({ status: phase })}
                className={cn(
                  "h-16 rounded-xl px-1 text-xs leading-tight font-bold",
                  on ? cn(PIECE_STATUS[phase].tone, "ring-2 ring-ink") : "border border-line bg-surface text-ink-muted",
                )}
              >
                {PIECE_STATUS[phase].short}
              </button>
            );
          })}
        </div>
        <p className="text-sm text-ink-muted">{PIECE_STATUS[current].label}</p>
      </section>

      {editable ? (
        <section aria-label="Datos de la pieza" className="grid gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1.5 text-sm font-medium">
            Responsable
            <select
              value={piece.assignee_user_id ?? ""}
              onChange={(e) => update.mutate({ assignee_user_id: e.currentTarget.value || null })}
              className="h-11 rounded-lg border border-line bg-surface px-2 text-base font-normal sm:text-sm"
            >
              <option value="">Sin responsable</option>
              {active.map((m) => (
                <option key={m.user_id} value={m.user_id}>
                  {m.name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1.5 text-sm font-medium">
            Vence
            <input
              type="date"
              defaultValue={piece.due_date ?? ""}
              onBlur={(e) => {
                const value = e.currentTarget.value || null;
                if (value !== piece.due_date) update.mutate({ due_date: value });
              }}
              className="h-11 rounded-lg border border-line bg-surface px-2 text-base font-normal sm:text-sm"
            />
          </label>
          <label className="flex flex-col gap-1.5 text-sm font-medium sm:col-span-2">
            Notas
            <textarea
              defaultValue={piece.notes ?? ""}
              rows={3}
              maxLength={2000}
              placeholder="Medidas, materiales, qué falta…"
              onBlur={(e) => {
                const value = e.currentTarget.value.trim() || null;
                if (value !== piece.notes) update.mutate({ notes: value });
              }}
              className="rounded-lg border border-line bg-surface px-3 py-2 text-base font-normal sm:text-sm"
            />
          </label>
        </section>
      ) : piece.notes ? (
        <p className="whitespace-pre-line text-sm">{piece.notes}</p>
      ) : null}

      {update.isError ? <Notice tone="error">{errorMessage(update.error)}</Notice> : null}
      {editable ? (
        <Button
          variant="ghost"
          className="self-start text-danger"
          loading={remove.isPending}
          onClick={() => window.confirm(`¿Borrar la pieza ${piece.name}?`) && remove.mutate()}
        >
          <Trash2 className="size-4" aria-hidden /> Borrar pieza
        </Button>
      ) : null}
      {remove.isError ? <Notice tone="error">{errorMessage(remove.error)}</Notice> : null}
    </div>
  );
}
