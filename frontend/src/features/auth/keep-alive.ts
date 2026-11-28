import { useEffect } from "react";

import { refreshSession } from "@/lib/api/client";

/** El pase de acceso dura 15 minutos: se renueva antes, en segundo plano. */
export const RENEW_EVERY_MS = 12 * 60_000;

/**
 * Renueva la sesión en segundo plano mientras la app está abierta, y al volver a ella si pasó
 * el tiempo. Así ninguna pantalla espera un "pase vencido → renovar → reintentar".
 */
export function useSessionKeepAlive() {
  useEffect(() => {
    let last = Date.now();
    const renew = () => {
      if (document.visibilityState !== "visible" || Date.now() - last < RENEW_EVERY_MS) return;
      last = Date.now();
      void refreshSession();
    };
    const timer = window.setInterval(renew, 60_000);
    document.addEventListener("visibilitychange", renew);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", renew);
    };
  }, []);
}
