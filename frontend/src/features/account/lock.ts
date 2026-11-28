/** Cuándo se bloquea la pantalla (si la persona activó el PIN). */
export const HIDDEN_LOCK_MS = 60_000; // minimizada más de 1 minuto (sacar una foto no la bloquea)
export const IDLE_LOCK_MS = 5 * 60_000; // 5 minutos sin tocar nada

const LAST = "handie-last-active";
const LOCKED = "handie-locked";

function get(storage: () => Storage, key: string): string | null {
  try {
    return storage().getItem(key);
  } catch {
    return null;
  }
}

function set(storage: () => Storage, key: string, value: string | null) {
  try {
    if (value === null) storage().removeItem(key);
    else storage().setItem(key, value);
  } catch {
    // modo privado: el bloqueo funciona igual mientras la pestaña está abierta
  }
}

export const lastActive = () => Number(get(() => localStorage, LAST) ?? 0);
export const markActive = (now = Date.now()) => set(() => localStorage, LAST, String(now));
export const wasLocked = () => get(() => sessionStorage, LOCKED) === "1";
export const rememberLocked = (locked: boolean) => set(() => sessionStorage, LOCKED, locked ? "1" : null);

/** ¿Hay que bloquear? Si estuvo minimizada o quieta más de la cuenta. */
export function shouldLock({
  now,
  last,
  hiddenSince,
}: {
  now: number;
  last: number;
  hiddenSince: number | null;
}): boolean {
  if (hiddenSince !== null && now - hiddenSince > HIDDEN_LOCK_MS) return true;
  return last > 0 && now - last > IDLE_LOCK_MS;
}
