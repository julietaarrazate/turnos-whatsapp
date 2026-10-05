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

let refreshing: Promise<boolean> | null = null;

/** Un solo refresh a la vez aunque varias requests reciban 401 juntas (evita el reuso). */
function refreshSession(): Promise<boolean> {
  refreshing ??= fetch("/api/v1/auth/refresh", {
    method: "POST",
    headers: CSRF_HEADERS,
    credentials: "same-origin",
  })
    .then((response) => response.ok)
    .catch(() => false)
    .finally(() => {
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
  if (await refreshSession()) return fetch(retry);
  redirectToLogin();
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
