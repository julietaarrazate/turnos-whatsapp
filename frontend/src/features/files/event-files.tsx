"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Camera, ExternalLink, FileText, Image as ImageIcon, Link2, Plus, Trash2, Upload } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Notice } from "@/components/ui/notice";
import { useSession } from "@/features/auth/session";
import { ApiError, api, errorMessage, unwrap } from "@/lib/api/client";
import type { Schemas } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatDate } from "@/lib/format/date";
import { MAX_UPLOAD_BYTES, shrinkImage, toBase64, uploadName } from "@/lib/files";
import { LIVE } from "@/lib/live";

type Item = Schemas["FileItem"];
type Category = Schemas["FileCategory"];

export const filesKey = (eventId: string) => ["event-files", eventId] as const;

/** Cómo se ordena la pestaña: lo del cliente arriba, las fotos del taller abajo. */
export const SECTIONS: { key: string; label: string; hint: string }[] = [
  { key: "CLIENT", label: "Del cliente", hint: "Brief, manual de marca, logos, referencias" },
  { key: "DESIGN", label: "Diseño", hint: "Renders y planos (la versión vigente arriba)" },
  { key: "ADMIN", label: "Administración", hint: "OC, permisos del predio, seguros, ART" },
  { key: "OTHER", label: "Otros", hint: "" },
  { key: "PROGRESS", label: "Avances", hint: "Fotos del taller y del montaje" },
];

const UPLOADABLE: { value: Category; label: string }[] = [
  { value: "CLIENT", label: "Del cliente" },
  { value: "DESIGN", label: "Diseño" },
  { value: "ADMIN", label: "Administración" },
  { value: "OTHER", label: "Otros" },
];

/** Agrupa por sección; en Diseño, las versiones viejas de un plano van al final. */
export function groupFiles(items: Item[]): { key: string; label: string; hint: string; items: Item[] }[] {
  return SECTIONS.map((section) => ({
    ...section,
    items: items
      .filter((item) => item.category === section.key)
      .sort((a, b) => Number(b.current !== false) - Number(a.current !== false)),
  })).filter((section) => section.items.length > 0);
}

function FileIcon({ item }: { item: Item }) {
  const Icon = item.source === "LINK" ? Link2 : item.source === "PHOTO" ? Camera : item.mime?.startsWith("image/") ? ImageIcon : FileText;
  return <Icon className="size-5 shrink-0 text-brand" aria-hidden />;
}

function FileRow({ item, eventId }: { item: Item; eventId: string }) {
  const queryClient = useQueryClient();
  const remove = useMutation({
    mutationFn: async () => unwrap(await api.DELETE("/api/v1/event-files/{file_id}", { params: { path: { file_id: item.id } } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: filesKey(eventId) }),
  });
  const old = item.current === false;
  return (
    <li className={cn("flex items-center gap-3 py-2.5", old && "opacity-60")}>
      <FileIcon item={item} />
      <a href={item.href} target="_blank" rel="noopener noreferrer" className="min-w-0 flex-1">
        <span className="flex items-center gap-1.5 font-semibold text-ink">
          <span className="truncate">{item.title}</span>
          {item.source === "LINK" ? <ExternalLink className="size-3.5 shrink-0 text-ink-muted" aria-label="(link)" /> : null}
        </span>
        <span className="block truncate text-xs text-ink-muted">
          {[item.piece_name, item.author_name, formatDate(item.created_at)].filter(Boolean).join(" · ")}
        </span>
        {item.expires_soon ? (
          <span className="mt-0.5 flex items-center gap-1 text-xs font-semibold text-warning">
            <AlertTriangle className="size-3.5" aria-hidden /> WeTransfer se vence en días: bajalo y subilo acá.
          </span>
        ) : null}
      </a>
      {item.version ? (
        <span
          className={cn(
            "shrink-0 rounded-md px-2 py-0.5 text-xs font-bold",
            item.current ? "bg-success/15 text-success" : "bg-subtle text-ink-muted",
          )}
        >
          v{item.version}
          {item.current ? " vigente" : ""}
        </span>
      ) : null}
      {item.can_delete ? (
        <button
          type="button"
          aria-label={`Sacar ${item.title}`}
          disabled={remove.isPending}
          onClick={() => window.confirm(`¿Sacar "${item.title}" de los archivos del evento?`) && remove.mutate()}
          className="flex size-10 shrink-0 items-center justify-center rounded-full text-ink-muted hover:bg-subtle hover:text-danger"
        >
          <Trash2 className="size-4" aria-hidden />
        </button>
      ) : null}
    </li>
  );
}

function AddFile({ eventId, pieces }: { eventId: string; pieces: { id: string; name: string }[] }) {
  const queryClient = useQueryClient();
  const { me } = useSession();
  const [mode, setMode] = useState<"file" | "link">(me.uploads_enabled ? "file" : "link");
  const [category, setCategory] = useState<Category>("CLIENT");
  const [title, setTitle] = useState("");
  const [pieceId, setPieceId] = useState("");
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const add = useMutation({
    mutationFn: async () => {
      let upload: Schemas["PhotoIn"] | null = null;
      if (mode === "file" && file) {
        const blob = file.type.startsWith("image/") ? await shrinkImage(file) : file;
        if (blob.size > MAX_UPLOAD_BYTES) throw new ApiError(413, "upload_too_large", "El archivo pesa más de 10 MB: pegá el link de Drive");
        upload = { filename: uploadName(file.name, blob), file_base64: await toBase64(blob) };
      }
      return unwrap(
        await api.POST("/api/v1/events/{event_id}/files", {
          params: { path: { event_id: eventId } },
          body: {
            category,
            title: title.trim() || file?.name || "Archivo",
            piece_id: pieceId || null,
            url: mode === "link" ? url.trim() : null,
            file: upload,
          },
        }),
      );
    },
    onSuccess: () => {
      setTitle("");
      setUrl("");
      setFile(null);
      void queryClient.invalidateQueries({ queryKey: filesKey(eventId) });
    },
  });
  const ready = mode === "link" ? url.trim().length > 8 && title.trim() : Boolean(file);
  return (
    <form
      aria-label="Agregar archivo"
      className="flex flex-col gap-3 rounded-xl border border-dashed border-line bg-surface p-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (ready) add.mutate();
      }}
    >
      <div role="group" aria-label="Cómo se agrega" className="grid grid-cols-2 gap-1 rounded-lg bg-subtle p-1">
        {(
          [
            ["file", "Subir archivo"],
            ["link", "Pegar link (Drive…)"],
          ] as const
        ).map(([value, label]) => (
          <button
            key={value}
            type="button"
            aria-pressed={mode === value}
            disabled={value === "file" && !me.uploads_enabled}
            onClick={() => setMode(value)}
            className={cn(
              "h-10 rounded-md text-sm font-semibold disabled:opacity-40",
              mode === value ? "bg-surface text-ink shadow-sm" : "text-ink-muted",
            )}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="flex flex-col gap-1.5 text-sm font-medium">
          Tipo
          <select
            value={category}
            onChange={(e) => setCategory(e.currentTarget.value as Category)}
            className="h-11 rounded-lg border border-line bg-surface px-2 text-base font-normal sm:text-sm"
          >
            {UPLOADABLE.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1.5 text-sm font-medium">
          Pieza (opcional)
          <select
            value={pieceId}
            onChange={(e) => setPieceId(e.currentTarget.value)}
            className="h-11 rounded-lg border border-line bg-surface px-2 text-base font-normal sm:text-sm"
          >
            <option value="">Todo el evento</option>
            {pieces.map((piece) => (
              <option key={piece.id} value={piece.id}>
                {piece.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      <label className="flex flex-col gap-1.5 text-sm font-medium">
        Nombre
        <input
          value={title}
          onChange={(e) => setTitle(e.currentTarget.value)}
          maxLength={200}
          placeholder={mode === "link" ? "Ej.: Manual de marca (Drive)" : "Si lo dejás vacío, va el nombre del archivo"}
          className="h-11 rounded-lg border border-line bg-surface px-3 text-base font-normal sm:text-sm"
        />
      </label>
      {mode === "link" ? (
        <label className="flex flex-col gap-1.5 text-sm font-medium">
          Link
          <input
            value={url}
            onChange={(e) => setUrl(e.currentTarget.value)}
            inputMode="url"
            placeholder="https://drive.google.com/…"
            className="h-11 rounded-lg border border-line bg-surface px-3 text-base font-normal sm:text-sm"
          />
        </label>
      ) : (
        <label className="flex h-11 cursor-pointer items-center gap-2 rounded-lg border border-line px-3 text-sm focus-within:outline-2 focus-within:outline-accent">
          <Upload className="size-4 shrink-0 text-brand" aria-hidden />
          <span className="truncate">{file ? file.name : "Elegir PDF o imagen (hasta 10 MB)"}</span>
          <input
            type="file"
            accept="application/pdf,image/*"
            aria-label="Archivo"
            className="sr-only"
            onChange={(e) => {
              setFile(e.currentTarget.files?.[0] ?? null);
              e.currentTarget.value = "";
            }}
          />
        </label>
      )}
      <Button type="submit" loading={add.isPending} disabled={!ready}>
        <Plus className="size-4" aria-hidden /> Agregar
      </Button>
      {add.isError ? <Notice tone="error">{errorMessage(add.error)}</Notice> : null}
      <p className="text-xs text-ink-muted">
        Lo pesado (Illustrator, Photoshop, videos) conviene dejarlo en Drive y pegar el link: así no se llena el espacio.
      </p>
    </form>
  );
}

/** Pestaña "Archivos" del evento: todo ordenado por tipo, pegado a la pieza cuando corresponde. */
export function EventFiles({ eventId }: { eventId: string }) {
  const files = useQuery({
    ...LIVE,
    queryKey: filesKey(eventId),
    queryFn: async () => unwrap(await api.GET("/api/v1/events/{event_id}/files", { params: { path: { event_id: eventId } } })),
  });
  const pieces = useQuery({
    queryKey: ["events", "pieces", eventId, "names"],
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/events/{event_id}/pieces", { params: { path: { event_id: eventId } } })),
  });
  const [adding, setAdding] = useState(false);
  if (files.isPending) return <p className="text-sm text-ink-muted">Cargando…</p>;
  if (files.isError) return <Notice tone="error">{errorMessage(files.error)}</Notice>;
  const groups = groupFiles(files.data.items);
  return (
    <div className="flex flex-col gap-5">
      {files.data.can_edit ? (
        adding ? (
          <AddFile eventId={eventId} pieces={(pieces.data?.pieces ?? []).map((p) => ({ id: p.id, name: p.name }))} />
        ) : (
          <Button variant="secondary" onClick={() => setAdding(true)} className="self-start">
            <Plus className="size-4" aria-hidden /> Agregar archivo o link
          </Button>
        )
      ) : null}
      {groups.length === 0 ? (
        <p className="rounded-xl border border-line bg-surface p-6 text-sm text-ink-muted">
          Todavía no hay archivos. Subí el brief o el manual de marca, o pegá el link de la carpeta de Drive.
        </p>
      ) : null}
      {groups.map((group) => (
        <section key={group.key} aria-label={group.label} className="rounded-xl border border-line bg-surface px-4 pt-3">
          <h2 className="font-bold text-brand">
            {group.label} <span className="font-normal text-ink-muted">· {group.items.length}</span>
          </h2>
          {group.hint ? <p className="text-xs text-ink-muted">{group.hint}</p> : null}
          <ul className="divide-y divide-line">
            {group.items.map((item) => (
              <FileRow key={`${item.source}-${item.id}`} item={item} eventId={eventId} />
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
