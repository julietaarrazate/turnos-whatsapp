"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Camera, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Notice } from "@/components/ui/notice";
import { useSession } from "@/features/auth/session";
import { ApiError, api, errorMessage, unwrap } from "@/lib/api/client";
import type { Schemas } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { LIVE } from "@/lib/live";
import { formatDateTime } from "@/lib/format/date";
import { MAX_UPLOAD_BYTES, shrinkImage, toBase64, uploadName } from "@/lib/files";

import { VoiceRecorder, voiceFilename } from "./voice-recorder";

type Update = Schemas["PieceUpdateOut"];

export const progressKey = (pieceId: string) => ["piece-progress", pieceId] as const;

/** Las fotos de avance se achican más que un comprobante: alcanza para ver el trabajo. */
const PHOTO = { maxSide: 1600, minBytes: 300 * 1024 };

export function photoUrl(updateId: string): string {
  return `/api/v1/piece-updates/${updateId}/photo`;
}

export function audioUrl(updateId: string): string {
  return `/api/v1/piece-updates/${updateId}/audio`;
}

export function usePieceProgress(pieceId: string) {
  return useQuery({
    ...LIVE,
    queryKey: progressKey(pieceId),
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/pieces/{piece_id}/updates", { params: { path: { piece_id: pieceId } } })),
  });
}

export function usePostProgress(onDone: () => void) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      pieceId,
      note,
      file,
      audio = null,
    }: {
      pieceId: string;
      note: string;
      file: File | null;
      audio?: Blob | null;
    }) => {
      let photo: Schemas["PhotoIn"] | null = null;
      if (file) {
        const blob = await shrinkImage(file, PHOTO);
        if (blob.size > MAX_UPLOAD_BYTES) throw new ApiError(413, "upload_too_large", "La foto pesa más de 10 MB");
        photo = { filename: uploadName(file.name, blob), file_base64: await toBase64(blob) };
      }
      return unwrap(
        await api.POST("/api/v1/pieces/{piece_id}/updates", {
          params: { path: { piece_id: pieceId } },
          body: {
            note: note.trim() || null,
            photo,
            audio: audio ? { filename: voiceFilename(audio.type), file_base64: await toBase64(audio) } : null,
          },
        }),
      );
    },
    onSuccess: (_, { pieceId }) => {
      void queryClient.invalidateQueries({ queryKey: progressKey(pieceId) });
      onDone();
    },
  });
}

/** Foto y/o nota. En el celular, "Sacar foto" abre la cámara trasera directo. */
export function ProgressForm({ pieceId, pieceName, onDone }: { pieceId: string; pieceName: string; onDone?: () => void }) {
  const { me } = useSession();
  const [note, setNote] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [audio, setAudio] = useState<Blob | null>(null);
  const [sent, setSent] = useState(false);
  const post = usePostProgress(() => {
    setNote("");
    setFile(null);
    setAudio(null);
    setSent(true);
    onDone?.();
  });

  const preview = useMemo(() => (file ? URL.createObjectURL(file) : null), [file]);
  useEffect(() => () => (preview ? URL.revokeObjectURL(preview) : undefined), [preview]);

  return (
    <form
      aria-label={`Subir avance de ${pieceName}`}
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        setSent(false);
        post.mutate({ pieceId, note, file, audio });
      }}
    >
      {me.uploads_enabled ? (
        preview ? (
          <div className="relative">
            {/* eslint-disable-next-line @next/next/no-img-element -- vista previa local (blob:) */}
            <img src={preview} alt="Foto elegida" className="max-h-72 w-full rounded-xl object-cover" />
            <button
              type="button"
              aria-label="Quitar la foto"
              onClick={() => setFile(null)}
              className="absolute top-2 right-2 flex size-11 items-center justify-center rounded-full bg-ink/70 text-white"
            >
              <X className="size-5" aria-hidden />
            </button>
          </div>
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
                setSent(false);
                setFile(next);
              }}
            />
          </label>
        )
      ) : (
        <p className="text-sm text-ink-muted">Las fotos se activan cuando se configure el espacio de archivos. Mientras, podés dejar una nota.</p>
      )}
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
      <Button type="submit" size="lg" loading={post.isPending} disabled={!file && !audio && !note.trim()}>
        Enviar avance
      </Button>
      {post.isError ? <Notice tone="error">{errorMessage(post.error)}</Notice> : null}
      {sent && !post.isPending ? <Notice tone="success">Avance enviado.</Notice> : null}
    </form>
  );
}

function UpdateItem({ update }: { update: Update }) {
  return (
    <li className="flex flex-col gap-1.5">
      {update.has_photo ? (
        <a href={photoUrl(update.id)} target="_blank" rel="noopener" className="block overflow-hidden rounded-xl bg-subtle">
          {/* eslint-disable-next-line @next/next/no-img-element -- la API sirve la foto con permiso de sesión */}
          <img
            src={photoUrl(update.id)}
            alt={`Foto de avance de ${update.author_name}`}
            loading="lazy"
            className="aspect-[4/3] w-full object-cover"
          />
        </a>
      ) : null}
      <p className="text-sm">
        <strong>{update.author_name}</strong>
        <span className="text-ink-muted"> · {formatDateTime(update.created_at)}</span>
      </p>
      {update.has_audio ? (
        <audio src={audioUrl(update.id)} controls preload="none" className="h-10 w-full" aria-label={`Nota de voz de ${update.author_name}`} />
      ) : null}
      {update.note ? <p className="text-sm whitespace-pre-line">{update.note}</p> : null}
    </li>
  );
}

/** "Avances" en la ficha de la pieza: lo más nuevo arriba y, a quien puede, el botón para subir. */
export function PieceProgress({ pieceId, pieceName, canPost }: { pieceId: string; pieceName: string; canPost: boolean }) {
  const updates = usePieceProgress(pieceId);
  const [open, setOpen] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    if (open) dialog.current?.showModal();
    else dialog.current?.close();
  }, [open]);

  return (
    <section aria-label="Avances" className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-semibold">Avances</h3>
        {canPost ? (
          <Button size="sm" onClick={() => setOpen(true)} className="bg-magenta hover:bg-magenta/90">
            <Camera className="size-4" aria-hidden /> Subir avance
          </Button>
        ) : null}
      </div>
      {updates.isPending ? <p className="text-sm text-ink-muted">Cargando…</p> : null}
      {updates.isError ? <Notice tone="error">{errorMessage(updates.error)}</Notice> : null}
      {updates.data && updates.data.length === 0 ? (
        <p className="text-sm text-ink-muted">Todavía no hay avances. Una foto vale más que un mensaje.</p>
      ) : null}
      {updates.data?.length ? (
        <ul className={cn("grid gap-4", "sm:grid-cols-2")}>
          {updates.data.map((update) => (
            <UpdateItem key={update.id} update={update} />
          ))}
        </ul>
      ) : null}
      {canPost ? (
        <dialog
          ref={dialog}
          aria-label={`Subir avance de ${pieceName}`}
          onClose={() => setOpen(false)}
          onClick={(e) => e.target === dialog.current && setOpen(false)}
          className="m-0 mt-auto w-full max-w-none rounded-t-2xl border-0 bg-surface p-0 backdrop:bg-ink/30 sm:m-auto sm:max-w-md sm:rounded-2xl"
        >
          <div className="flex flex-col gap-3 px-4 pt-3 pb-[calc(1.5rem+env(safe-area-inset-bottom))]">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-bold">Avance · {pieceName}</h2>
              <button
                type="button"
                aria-label="Cerrar"
                onClick={() => setOpen(false)}
                className="flex size-11 items-center justify-center rounded-full text-ink-muted hover:bg-subtle"
              >
                <X className="size-5" aria-hidden />
              </button>
            </div>
            {open ? <ProgressForm pieceId={pieceId} pieceName={pieceName} onDone={() => setOpen(false)} /> : null}
          </div>
        </dialog>
      ) : null}
    </section>
  );
}
