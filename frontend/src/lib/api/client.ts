import createClient from "openapi-fetch";

import type { paths } from "./schema";

/** Error de la API en formato problem+json (ARCHITECTURE §4.5). La UI decide por `code`. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    readonly detail: string,
    readonly errors?: { loc: (string | number)[]; msg: string }[],
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

const CSRF_HEADERS = { "X-Requested-With": "fetch" };
// Endpoints donde un 401 es una respuesta legítima, no una sesión vencida.
const NO_REFRESH = ["/api/v1/auth/login", "/api/v1/auth/refresh", "/api/v1/auth/logout"];

export type RefreshResult = "ok" | "expired" | "unavailable";

/** Esperas entre reintentos mientras el servidor gratuito se despierta (~1 minuto en total). */
export const WAKE_DELAYS_MS = [2_000, 4_000, 8_000, 15_000, 30_000];

/**
 * Renovar la sesión. Solo un 401/403 significa "vencida, volver a ingresar". Un 5xx o un corte
 * de red es el servidor que todavía no despertó (Render gratis duerme): se reintenta un rato en
 * vez de mandar a la pantalla de ingreso por nada.
 */
export async function renewSession(
  doFetch: () => Promise<Response>,
  delays: readonly number[] = WAKE_DELAYS_MS,
  wait: (ms: number) => Promise<void> = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
): Promise<RefreshResult> {
  for (let attempt = 0; ; attempt++) {
    let status: number | null = null;
    try {
      status = (await doFetch()).status;
    } catch {
      status = null; // sin red o el servidor no contestó
    }
    if (status !== null && status >= 200 && status < 300) return "ok";
    if (status === 401 || status === 403) return "expired";
    if (attempt >= delays.length) return "unavailable";
    await wait(delays[attempt]);
  }
}

let refreshing: Promise<RefreshResult> | null = null;

/** Un solo refresh a la vez aunque varias requests reciban 401 juntas (evita el reuso). */
function refreshSession(): Promise<RefreshResult> {
  refreshing ??= renewSession(() =>
    fetch("/api/v1/auth/refresh", { method: "POST", headers: CSRF_HEADERS, credentials: "same-origin" }),
  ).finally(() => {
    refreshing = null;
  });
  return refreshing;
}

function redirectToLogin(): void {
  if (typeof window === "undefined" || window.location.pathname === "/login") return;
  const next = encodeURIComponent(window.location.pathname + window.location.search);
  // Fuera de React no hay router; además una recarga completa descarta el estado en memoria.
  // eslint-disable-next-line @next/next/no-location-assign-relative-destination
  window.location.assign(`/login?next=${next}`);
}

async function fetchWithRefresh(request: Request): Promise<Response> {
  const retry = request.clone();
  const response = await fetch(request);
  const path = new URL(request.url).pathname;
  if (response.status !== 401 || NO_REFRESH.some((p) => path.startsWith(p))) return response;
  const renewed = await refreshSession();
  if (renewed === "ok") return fetch(retry);
  // Solo una sesión realmente vencida lleva al ingreso; si el servidor no despertó, la pantalla
  // muestra el error con "Reintentar" y la sesión sigue.
  if (renewed === "expired") redirectToLogin();
  return response;
}

export const api = createClient<paths>({
  baseUrl: typeof window === "undefined" ? "http://localhost" : window.location.origin,
  fetch: fetchWithRefresh,
  headers: CSRF_HEADERS,
  credentials: "same-origin",
});

type ApiResult<T> = { data?: T; error?: unknown; response: Response };

/** Devuelve `data` o lanza `ApiError` con el problem+json del backend. */
export function unwrap<T>(result: ApiResult<T>): T {
  const { data, error, response } = result;
  if (error !== undefined || !response.ok) {
    const problem = (error ?? {}) as Partial<{
      code: string;
      detail: string;
      errors: ApiError["errors"];
    }>;
    throw new ApiError(
      response.status,
      problem.code ?? "http_error",
      problem.detail ?? "Ocurrió un error inesperado",
      problem.errors,
    );
  }
  return data as T;
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.detail;
  return "No pudimos conectarnos. Revisá tu conexión e intentá de nuevo.";
}
