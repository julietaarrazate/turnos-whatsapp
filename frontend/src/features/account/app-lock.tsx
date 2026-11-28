"use client";

import { Delete, Fingerprint } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { HandieMark } from "@/components/brand/handie-logo";
import { useSession } from "@/features/auth/session";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import { cn } from "@/lib/cn";

import { lastActive, markActive, rememberLocked, shouldLock, wasLocked } from "./lock";
import { loginWithPasskey, passkeyHere, passkeysAvailable, wasCancelled } from "./passkeys";

const KEYS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "", "0", "del"] as const;

function LockScreen({ onUnlock }: { onUnlock: () => void }) {
  const { me, logout } = useSession();
  const router = useRouter();
  const [pin, setPin] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [canBio, setCanBio] = useState(false);

  const unlockWithBio = useCallback(async () => {
    setError(null);
    try {
      const next = await loginWithPasskey();
      if (next.user.id === me.user.id) onUnlock();
      else setError("Esa huella es de otra cuenta.");
    } catch (err) {
      if (!wasCancelled(err)) setError(errorMessage(err));
    }
  }, [me.user.id, onUnlock]);

  useEffect(() => {
    void passkeysAvailable().then((ok) => setCanBio(ok && passkeyHere()));
  }, []);

  async function check(value: string) {
    setBusy(true);
    setError(null);
    try {
      const result = unwrap(await api.POST("/api/v1/auth/pin/check", { body: { pin: value } }));
      if (result.ok) return onUnlock();
      if (result.attempts_left === 0) {
        // 5 intentos mal: el servidor ya cerró la sesión.
        router.replace("/login");
        return;
      }
      setError(`PIN incorrecto. ${result.attempts_left === 1 ? "Te queda 1 intento" : `Te quedan ${result.attempts_left} intentos`}.`);
      setPin("");
    } catch (err) {
      setError(errorMessage(err));
      setPin("");
    } finally {
      setBusy(false);
    }
  }

  function press(key: string) {
    if (busy) return;
    if (key === "del") return setPin((p) => p.slice(0, -1));
    if (!key || pin.length >= 4) return;
    const next = pin + key;
    setPin(next);
    if (next.length === 4) void check(next);
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Handie está bloqueada"
      className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-6 bg-canvas px-6 pt-[env(safe-area-inset-top)] pb-[env(safe-area-inset-bottom)]"
      onKeyDown={(e) => {
        if (/^\d$/.test(e.key)) press(e.key);
        if (e.key === "Backspace") press("del");
      }}
      tabIndex={-1}
    >
      <HandieMark className="size-16" />
      <div className="text-center">
        <p className="text-lg font-bold">Hola, {me.user.name.split(" ")[0]}</p>
        <p className="text-sm text-ink-muted">Ingresá tu PIN para seguir</p>
      </div>
      <div aria-label={`${pin.length} de 4 números`} className="flex gap-4" role="status">
        {[0, 1, 2, 3].map((i) => (
          <span key={i} className={cn("size-4 rounded-full border-2 border-brand", i < pin.length && "bg-brand")} />
        ))}
      </div>
      <p aria-live="assertive" className="min-h-5 text-center text-sm font-semibold text-danger">
        {error}
      </p>
      <div className="grid grid-cols-3 gap-3">
        {KEYS.map((key, i) =>
          key === "" ? (
            <span key={i} />
          ) : (
            <button
              key={key}
              type="button"
              aria-label={key === "del" ? "Borrar" : key}
              disabled={busy}
              onClick={() => press(key)}
              className="flex size-18 items-center justify-center rounded-full bg-surface text-2xl font-semibold shadow-sm active:bg-subtle"
            >
              {key === "del" ? <Delete className="size-6" aria-hidden /> : key}
            </button>
          ),
        )}
      </div>
      <div className="flex flex-col items-center gap-2">
        {canBio ? (
          <button type="button" onClick={() => void unlockWithBio()} className="flex items-center gap-2 font-semibold text-brand">
            <Fingerprint className="size-5" aria-hidden /> Usar huella o cara
          </button>
        ) : null}
        <button type="button" onClick={() => void logout()} className="text-sm text-ink-muted underline">
          Salir y entrar con otra cuenta
        </button>
      </div>
    </div>
  );
}

/** Tapa la app cuando se minimiza más de 1 minuto o queda quieta 5: la sesión sigue abierta. */
export function AppLock() {
  const { me } = useSession();
  const enabled = me.pin_enabled ?? false;
  const [locked, setLocked] = useState(false);
  const hiddenSince = useRef<number | null>(null);

  const lock = useCallback(() => {
    rememberLocked(true);
    setLocked(true);
  }, []);

  useEffect(() => {
    if (!enabled) {
      rememberLocked(false);
      return;
    }
    // Al abrir la app: bloqueada si quedó bloqueada o si pasó mucho desde la última vez.
    if (wasLocked() || shouldLock({ now: Date.now(), last: lastActive(), hiddenSince: null })) queueMicrotask(lock);
    else markActive();

    let lastMark = 0;
    const active = () => {
      const now = Date.now();
      if (now - lastMark > 5_000) {
        lastMark = now;
        markActive(now);
      }
    };
    const visibility = () => {
      if (document.visibilityState === "hidden") {
        hiddenSince.current = Date.now();
        return;
      }
      if (shouldLock({ now: Date.now(), last: lastActive(), hiddenSince: hiddenSince.current })) lock();
      hiddenSince.current = null;
    };
    const idle = window.setInterval(() => {
      if (document.visibilityState === "visible" && shouldLock({ now: Date.now(), last: lastActive(), hiddenSince: null })) lock();
    }, 15_000);
    const events = ["pointerdown", "keydown", "scroll", "touchstart"] as const;
    events.forEach((name) => window.addEventListener(name, active, { passive: true }));
    document.addEventListener("visibilitychange", visibility);
    return () => {
      window.clearInterval(idle);
      events.forEach((name) => window.removeEventListener(name, active));
      document.removeEventListener("visibilitychange", visibility);
    };
  }, [enabled, lock]);

  if (!enabled || !locked) return null;
  return (
    <LockScreen
      onUnlock={() => {
        markActive();
        rememberLocked(false);
        setLocked(false);
      }}
    />
  );
}
