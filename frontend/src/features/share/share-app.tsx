"use client";

import { Share2 } from "lucide-react";
import { useState } from "react";

import { cn } from "@/lib/cn";

export const SHARE_TEXT = "Te paso Handie: presupuestos, producción y montaje de eventos, en un solo lugar.";

export function shareUrl(origin: string): string {
  return `${origin}/login?ref=compartir`;
}

/** Link de WhatsApp con el mensaje armado (para computadoras sin "Compartir" del sistema). */
export function whatsappShareUrl(url: string, text = SHARE_TEXT): string {
  return `https://wa.me/?text=${encodeURIComponent(`${text}\n${url}`)}`;
}

/**
 * "Recomendar Handie": en el teléfono abre el menú de compartir del sistema (WhatsApp, Instagram,
 * mail...); donde no existe, abre WhatsApp con el mensaje listo. El link lleva la miniatura de Handie.
 */
export function ShareApp({ className }: { className?: string }) {
  const [shared, setShared] = useState(false);

  async function share() {
    // Directo a la página de ingreso (sin redirección) y con una dirección que WhatsApp no tiene
    // guardada de antes, así la vista previa sale con la miniatura de Handie.
    const url = shareUrl(window.location.origin);
    if (typeof navigator.share === "function") {
      try {
        await navigator.share({ title: "Handie", text: SHARE_TEXT, url });
        setShared(true);
      } catch {
        // La persona cerró el menú: no pasa nada.
      }
      return;
    }
    window.open(whatsappShareUrl(url), "_blank", "noopener");
    setShared(true);
  }

  return (
    <button
      type="button"
      onClick={() => void share()}
      className={cn(
        "flex min-h-11 w-full items-center justify-center gap-2 rounded-xl border border-line px-3 text-sm font-semibold text-ink hover:bg-subtle",
        className,
      )}
    >
      <Share2 className="size-4" aria-hidden />
      {shared ? "¡Gracias por recomendar Handie!" : "Recomendar Handie"}
    </button>
  );
}
