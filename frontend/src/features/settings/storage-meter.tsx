"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";

import { api, unwrap } from "@/lib/api/client";
import { cn } from "@/lib/cn";
import { formatSize } from "@/lib/files";

export const STORAGE_KEY = ["documents", "storage"] as const;

export function useStorage() {
  return useQuery({
    queryKey: STORAGE_KEY,
    queryFn: async () => unwrap(await api.GET("/api/v1/documents/storage")),
    staleTime: 60_000,
  });
}

export function usedPercent(used: number, limit: number): number {
  return limit > 0 ? Math.min(100, Math.round((used * 100) / limit)) : 0;
}

/** "Usaste 1,2 GB de 8 GB": cuánto ocupan los archivos y el tope (Configuración → Organización). */
export function StorageMeter() {
  const storage = useStorage();
  if (!storage.data) return null;
  const { used, limit, enabled, warn, today_used, today_limit } = storage.data;
  const percent = usedPercent(used, limit);
  return (
    <section aria-label="Espacio de archivos" className="flex flex-col gap-2 rounded-xl border border-line bg-surface p-4">
      <h2 className="font-semibold">Espacio de archivos</h2>
      {!enabled ? (
        <p className="text-sm text-ink-muted">Todavía no está conectado el espacio de archivos (fotos, notas de voz, planos). Los links de Drive funcionan igual.</p>
      ) : null}
      <p className="text-sm">
        Usaste <strong>{formatSize(used)}</strong> de {formatSize(limit)} ({percent} %).
      </p>
      <div className="h-2.5 overflow-hidden rounded-full bg-subtle" role="progressbar" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100} aria-label="Espacio usado">
        <div className={cn("h-full rounded-full", warn ? "bg-warning" : "bg-fill")} style={{ width: `${percent}%` }} />
      </div>
      <p className="text-xs text-ink-muted">
        Hoy se subieron {formatSize(today_used)} (freno diario: {formatSize(today_limit)}). Fotos y voz se achican solas; planos y archivos, hasta 5 MB cada uno.
      </p>
    </section>
  );
}

/** Aviso en el inicio cuando el espacio pasa el 80 %, para quien puede decidir qué liberar. */
export function StorageWarning() {
  const storage = useStorage();
  if (!storage.data?.warn) return null;
  const percent = usedPercent(storage.data.used, storage.data.limit);
  return (
    <p role="status" className="flex items-start gap-2 rounded-xl border border-warning/40 bg-warning/10 p-3 text-sm">
      <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
      <span>
        El espacio de archivos está al <strong>{percent} %</strong>. Conviene dejar lo pesado en Drive con su link y, de los
        eventos cerrados, descargar las fotos y liberarlas.
      </span>
    </p>
  );
}
