"use client";

import { RefreshCw } from "lucide-react";
import Link from "next/link";
import { useEffect } from "react";

import { Button, buttonClasses } from "@/components/ui/button";

/** Si una pantalla falla, se queda dentro de la app (menú incluido) y se puede reintentar. */
export default function AppError({ error, retry }: { error: unknown; retry: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);
  return (
    <section role="alert" className="mx-auto flex max-w-md flex-col items-start gap-3 rounded-2xl border border-line bg-surface p-6">
      <h1 className="text-xl font-bold tracking-tight">No se pudo cargar esta pantalla</h1>
      <p className="text-sm text-ink-muted">
        Puede ser la conexión o que el servidor se esté actualizando. Probá de nuevo en unos segundos.
      </p>
      <div className="flex flex-wrap gap-2">
        <Button size="lg" onClick={() => retry()}>
          <RefreshCw className="size-4" aria-hidden /> Reintentar
        </Button>
        <Link href="/" className={buttonClasses("secondary", "lg")}>
          Ir al inicio
        </Link>
      </div>
    </section>
  );
}
