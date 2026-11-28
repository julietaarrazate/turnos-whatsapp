import { buildPolicy } from "./csp-policy.mjs";

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
 * CSP estricta (ARCHITECTURE §8.3) para las páginas que se arman en el momento (propuesta y link
 * de aprobación públicos, invitación): scripts solo con el nonce del request ('strict-dynamic'
 * deja cargar los chunks que esos scripts piden), nada de 'unsafe-inline'. Las páginas armadas de
 * antemano usan la huella de cada script (scripts/csp-hashes.mjs). En desarrollo React necesita
 * eval y estilos inline.
 */
export function contentSecurityPolicy(nonce: string, dev = false, sentry = sentryOrigin()): string {
  return buildPolicy({
    scriptSrc: `'self' 'nonce-${nonce}' 'strict-dynamic'${dev ? " 'unsafe-eval'" : ""}`,
    styleSrc: `'self' ${dev ? "'unsafe-inline'" : `'nonce-${nonce}'`}`,
    sentry,
  });
}
