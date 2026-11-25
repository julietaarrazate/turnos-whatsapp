/** Origen del ingest de Sentry (solo si hay DSN): el SDK manda los eventos ahí. */
export function sentryOrigin(dsn: string | undefined = process.env.NEXT_PUBLIC_SENTRY_DSN): string | null {
  if (!dsn) return null;
  try {
    return new URL(dsn).origin;
  } catch {
    return null;
  }
}

/**
 * CSP estricta (ARCHITECTURE §8.3): scripts solo con el nonce del request ('strict-dynamic' deja
 * cargar los chunks que esos scripts piden), nada de 'unsafe-inline'. El API va por el mismo origen
 * (rewrite a /api). En desarrollo React necesita eval y estilos inline.
 */
export function contentSecurityPolicy(nonce: string, dev = false, sentry = sentryOrigin()): string {
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${dev ? " 'unsafe-eval'" : ""}`,
    `style-src 'self' ${dev ? "'unsafe-inline'" : `'nonce-${nonce}'`}`,
    "img-src 'self' blob: data:",
    "font-src 'self'",
    `connect-src 'self'${sentry ? ` ${sentry}` : ""}`,
    "worker-src 'self'",
    "manifest-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join("; ");
}
