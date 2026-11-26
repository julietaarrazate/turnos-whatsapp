"use client";

import { Mic, Square, Trash2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { cn } from "@/lib/cn";

export const MAX_SECONDS = 60;

/** Lo que graba cada navegador: Chrome/Android WebM, Safari/iPhone MP4, Firefox Ogg. */
const CANDIDATES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];

export function pickMimeType(isSupported: (type: string) => boolean): string | undefined {
  return CANDIDATES.find((type) => isSupported(type));
}

/** "nota.webm", "nota.m4a" o "nota.ogg" según lo que grabó el navegador. */
export function voiceFilename(type: string): string {
  if (type.includes("mp4")) return "nota.m4a";
  if (type.includes("ogg")) return "nota.ogg";
  return "nota.webm";
}

export function formatSeconds(total: number): string {
  const s = Math.max(0, Math.floor(total));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

type State = { kind: "idle" } | { kind: "recording"; seconds: number } | { kind: "error"; message: string };

/**
 * Grabar una nota de voz: tocar para empezar, tocar para cortar (o se corta sola al minuto).
 * Se escucha antes de mandar y se puede borrar. Nada sale del teléfono hasta "Enviar avance".
 */
export function VoiceRecorder({ value, onChange }: { value: Blob | null; onChange: (blob: Blob | null) => void }) {
  const [state, setState] = useState<State>({ kind: "idle" });
  const recorder = useRef<MediaRecorder | null>(null);
  const timer = useRef<number | null>(null);
  const url = useMemo(() => (value ? URL.createObjectURL(value) : null), [value]);
  useEffect(() => () => (url ? URL.revokeObjectURL(url) : undefined), [url]);
  useEffect(
    () => () => {
      if (timer.current) window.clearInterval(timer.current);
      recorder.current?.stream.getTracks().forEach((track) => track.stop());
    },
    [],
  );

  const stop = () => {
    if (timer.current) window.clearInterval(timer.current);
    timer.current = null;
    if (recorder.current?.state === "recording") recorder.current.stop();
  };

  const start = async () => {
    if (typeof MediaRecorder === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      setState({ kind: "error", message: "Este teléfono no permite grabar desde la app. Escribí la nota." });
      return;
    }
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setState({ kind: "error", message: "Sin permiso para usar el micrófono. Activalo en la configuración del navegador." });
      return;
    }
    const mimeType = pickMimeType((type) => MediaRecorder.isTypeSupported(type));
    const media = new MediaRecorder(stream, mimeType ? { mimeType, audioBitsPerSecond: 32_000 } : undefined);
    const chunks: Blob[] = [];
    media.ondataavailable = (event) => event.data.size && chunks.push(event.data);
    media.onstop = () => {
      stream.getTracks().forEach((track) => track.stop());
      setState({ kind: "idle" });
      onChange(new Blob(chunks, { type: media.mimeType || mimeType || "audio/webm" }));
    };
    recorder.current = media;
    media.start();
    const started = Date.now();
    setState({ kind: "recording", seconds: 0 });
    timer.current = window.setInterval(() => {
      const seconds = (Date.now() - started) / 1000;
      if (seconds >= MAX_SECONDS) stop();
      else setState({ kind: "recording", seconds });
    }, 250);
  };

  if (value && url) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-line p-2">
        <audio src={url} controls className="h-10 min-w-0 flex-1" aria-label="Nota de voz grabada" />
        <button
          type="button"
          aria-label="Borrar la nota de voz"
          onClick={() => onChange(null)}
          className="flex size-11 shrink-0 items-center justify-center rounded-full text-ink-muted hover:bg-subtle hover:text-danger"
        >
          <Trash2 className="size-5" aria-hidden />
        </button>
      </div>
    );
  }
  const recording = state.kind === "recording";
  return (
    <div className="flex flex-col gap-1.5">
      <button
        type="button"
        onClick={recording ? stop : () => void start()}
        aria-pressed={recording}
        className={cn(
          "flex h-12 items-center justify-center gap-2 rounded-xl border text-base font-semibold",
          recording ? "border-danger bg-danger-fill text-white" : "border-line bg-surface text-ink hover:bg-subtle",
        )}
      >
        {recording ? <Square className="size-5" aria-hidden /> : <Mic className="size-5 text-magenta" aria-hidden />}
        {recording ? `Cortar · ${formatSeconds(state.seconds)} de ${formatSeconds(MAX_SECONDS)}` : "Grabar nota de voz"}
      </button>
      {state.kind === "error" ? <p className="text-sm text-danger">{state.message}</p> : null}
    </div>
  );
}
