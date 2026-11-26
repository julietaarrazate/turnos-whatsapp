"use client";

import { useQuery } from "@tanstack/react-query";
import { Camera, X } from "lucide-react";
import { usePathname } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Notice } from "@/components/ui/notice";
import { useSession } from "@/features/auth/session";
import { PIECE_STATUS } from "@/features/events/event-pieces";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import { cn } from "@/lib/cn";

import { usePostProgress } from "./piece-progress";
import { VoiceRecorder } from "./voice-recorder";

const PIECE_PAGE = /^\/events\/[^/]+\/pieces\/([^/]+)$/;

/** Abre la cámara desde cualquier pantalla: se saca la foto y después se elige la pieza.
 * `onSent` avisa que se mandó (para mostrar la confirmación con el diálogo ya cerrado). */
export function QuickPhotoDialog({ open, onClose, onSent }: { open: boolean; onClose: () => void; onSent: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (open) dialog.current?.showModal();
    else dialog.current?.close();
  }, [open]);
  return (
    <dialog
      ref={dialog}
      aria-label="Foto de avance"
      onClose={onClose}
      onClick={(e) => e.target === dialog.current && onClose()}
      className="m-0 mt-auto max-h-[92dvh] w-full max-w-none rounded-t-2xl border-0 bg-surface p-0 backdrop:bg-ink/30 sm:m-auto sm:max-w-md sm:rounded-2xl"
    >
      {open ? (
        <QuickPhoto
          onClose={onClose}
          onSent={() => {
            onSent();
            onClose();
          }}
        />
      ) : null}
    </dialog>
  );
}

function QuickPhoto({ onClose, onSent }: { onClose: () => void; onSent: () => void }) {
  const { me } = useSession();
  const pathname = usePathname();
  const [file, setFile] = useState<File | null>(null);
  const [note, setNote] = useState("");
  const [audio, setAudio] = useState<Blob | null>(null);
  // En la ficha de una pieza, la foto va a esa pieza (se puede cambiar).
  const [pieceId, setPieceId] = useState<string | null>(() => PIECE_PAGE.exec(pathname)?.[1] ?? null);
  const preview = useMemo(() => (file ? URL.createObjectURL(file) : null), [file]);
  useEffect(() => () => (preview ? URL.revokeObjectURL(preview) : undefined), [preview]);
  const pieces = useQuery({
    queryKey: ["pieces", "open"],
    queryFn: async () => unwrap(await api.GET("/api/v1/pieces/open")),
  });
  const post = usePostProgress(onSent);

  return (
    <form
      aria-label="Subir foto de avance"
      className="flex flex-col gap-3 px-4 pt-3 pb-[calc(1.5rem+env(safe-area-inset-bottom))]"
      onSubmit={(e) => {
        e.preventDefault();
        if (pieceId) post.mutate({ pieceId, note, file, audio });
      }}
    >
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold">Foto de avance</h2>
        <button
          type="button"
          aria-label="Cerrar"
          onClick={onClose}
          className="flex size-11 items-center justify-center rounded-full text-ink-muted hover:bg-subtle"
        >
          <X className="size-5" aria-hidden />
        </button>
      </div>

      {!me.uploads_enabled ? (
        <p className="text-sm text-ink-muted">Las fotos se activan cuando se configure el espacio de archivos. Mientras, podés dejar una nota.</p>
      ) : preview ? (
        // eslint-disable-next-line @next/next/no-img-element -- vista previa local (blob:)
        <img src={preview} alt="Foto elegida" className="max-h-56 w-full rounded-xl object-cover" />
      ) : (
        <label className="flex h-16 cursor-pointer items-center justify-center gap-2 rounded-xl bg-magenta text-lg font-bold text-white focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-ink">
          <Camera className="size-6" aria-hidden />
          Sacar foto
          <input
            type="file"
            accept="image/*"
            capture="environment"
            aria-label="Foto del avance"
            className="sr-only"
            onChange={(e) => {
              const next = e.currentTarget.files?.[0] ?? null;
              e.currentTarget.value = "";
              setFile(next);
            }}
          />
        </label>
      )}

      <fieldset className="flex min-h-0 flex-col gap-1.5">
        <legend className="mb-1.5 text-sm font-medium">¿De qué pieza?</legend>
        {pieces.isPending ? <p className="text-sm text-ink-muted">Cargando…</p> : null}
        {pieces.isError ? <Notice tone="error">{errorMessage(pieces.error)}</Notice> : null}
        {pieces.data && pieces.data.length === 0 ? (
          <p className="text-sm text-ink-muted">No hay piezas sin montar en eventos aprobados o en producción.</p>
        ) : null}
        <ul className="flex max-h-56 flex-col gap-1.5 overflow-y-auto">
          {pieces.data?.map((piece) => (
            <li key={piece.id}>
              <label
                className={cn(
                  "flex min-h-12 cursor-pointer items-center gap-3 rounded-xl border px-3 py-2",
                  pieceId === piece.id ? "border-brand bg-brand/[0.06]" : "border-line",
                )}
              >
                <input
                  type="radio"
                  name="piece"
                  value={piece.id}
                  checked={pieceId === piece.id}
                  onChange={() => setPieceId(piece.id)}
                  className="size-5 accent-brand"
                />
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-semibold">{piece.name}</span>
                  <span className="block truncate text-xs text-ink-muted">
                    {piece.mine ? "Tuya · " : ""}#{piece.event.number} {piece.event.name}
                  </span>
                </span>
                <span className={cn("shrink-0 rounded-md px-2 py-0.5 text-[11px] font-bold", PIECE_STATUS[piece.status].tone)}>
                  {PIECE_STATUS[piece.status].short}
                </span>
              </label>
            </li>
          ))}
        </ul>
      </fieldset>

      {me.uploads_enabled ? <VoiceRecorder value={audio} onChange={setAudio} /> : null}
      <label className="flex flex-col gap-1.5 text-sm font-medium">
        Nota (opcional)
        <textarea
          value={note}
          onChange={(e) => setNote(e.currentTarget.value)}
          maxLength={1000}
          rows={2}
          placeholder="Ej.: letras cortadas, mañana cableado LED"
          className="rounded-lg border border-line bg-surface px-3 py-2 text-base font-normal sm:text-sm"
        />
      </label>
      <Button type="submit" size="lg" loading={post.isPending} disabled={!pieceId || (!file && !audio && !note.trim())}>
        Enviar avance
      </Button>
      {post.isError ? <Notice tone="error">{errorMessage(post.error)}</Notice> : null}
    </form>
  );
}
