/** Rutas cuyo último segmento es un token secreto (no debe llegar a Sentry ni a logs). */
const TOKEN_PATHS = /\/(invite|reset-password|invitations)\/(?!accept\b)[^/?#]+/g;

export function redactTokens(url: string): string {
  return url.replace(TOKEN_PATHS, "/$1/[token]");
}

/** Configuración común de Sentry: no recolecta cookies, headers, cuerpos ni datos de usuario. */
export const SENTRY_DATA_COLLECTION = {
  userInfo: false,
  cookies: false,
  httpHeaders: false,
  httpBodies: [],
  urlQueryParams: false,
} as const;
