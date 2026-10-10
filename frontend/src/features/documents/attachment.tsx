"use client";

import { useMutation } from "@tanstack/react-query";
import { Camera, Paperclip, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Notice } from "@/components/ui/notice";
import { ApiError, api, errorMessage, unwrap } from "@/lib/api/client";
import type { Schemas } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatSize, MAX_UPLOAD_BYTES, shrinkImage, toBase64, uploadName } from "@/lib/files";

export type UploadedDocument = Schemas["DocumentOut"];
type Kind = "receipts" | "purchase-orders";

export const ACCEPT = "image/*,application/pdf";

/** Sube una foto (achicada) o un PDF; el archivo queda listo para adjuntar a un gasto o a una OC. */
export function useUpload(kind: Kind, onUploaded: (document: UploadedDocument) => void) {
  return useMutation({
    mutationFn: async (file: File) => {
      const blob = await shrinkImage(file);
      if (blob.size > MAX_UPLOAD_BYTES) throw new ApiError(413, "upload_too_large", "El archivo pesa más de 10 MB");
      const body = { filename: uploadName(file.name, blob), file_base64: await toBase64(blob) };
      return kind === "receipts"
        ? unwrap(await api.POST("/api/v1/documents/receipts", { body }))
        : unwrap(await api.POST("/api/v1/documents/purchase-orders", { body }));
    },
    onSuccess: onUploaded,
  });
}

type Upload = ReturnType<typeof useUpload>;

/** Campo "adjuntar": en el celular abre la cámara o la galería; también acepta PDF. */
export function AttachmentField({
  label,
  value,
  upload,
  onRemove,
}: {
  label: string;
  value: UploadedDocument | null;
  upload: Upload;
  onRemove: () => void;
}) {
  return (
    <div className="flex flex-col gap-1 text-sm">
      <span className="text-ink-muted">{label}</span>
      {value ? (
        <div className="flex min-h-11 items-center gap-2 rounded-lg border border-line px-3 sm:min-h-10">
          <Paperclip className="size-4 shrink-0 text-accent" aria-hidden />
          <span className="min-w-0 flex-1 truncate">{value.filename}</span>
          <span className="text-xs text-ink-muted">{formatSize(value.size)}</span>
          <Button type="button" size="sm" variant="ghost" aria-label={`Quitar ${value.filename}`} onClick={onRemove}>
            <X className="size-4" aria-hidden />
          </Button>
        </div>
      ) : (
        <label
          className={cn(
            "flex min-h-11 cursor-pointer items-center gap-2 rounded-lg border border-dashed border-line px-3 hover:bg-subtle focus-within:outline-2 focus-within:outline-accent sm:min-h-10",
            upload.isPending && "pointer-events-none opacity-60",
          )}
        >
          <Camera className="size-4 text-accent" aria-hidden />
          <span>{upload.isPending ? "Subiendo…" : "Sacar foto o elegir archivo (PDF)"}</span>
          <input
            type="file"
            accept={ACCEPT}
            aria-label={label}
            className="sr-only"
            disabled={upload.isPending}
            onChange={(e) => {
              const file = e.currentTarget.files?.[0];
              e.currentTarget.value = "";
              if (file) upload.mutate(file);
            }}
          />
        </label>
      )}
      {upload.isError ? <Notice tone="error">{errorMessage(upload.error)}</Notice> : null}
    </div>
  );
}

/** Link para ver el archivo en otra pestaña (la API lo sirve con el permiso de quien lo pide). */
export function AttachmentLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noopener" className="inline-flex items-center gap-1 text-accent underline-offset-2 hover:underline">
      <Paperclip className="size-3.5" aria-hidden />
      {children}
    </a>
  );
}
