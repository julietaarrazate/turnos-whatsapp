// Política de seguridad del contenido (CSP), compartida por el proxy (páginas armadas en el
// momento: con nonce) y por scripts/csp-hashes.mjs (páginas armadas de antemano: con la huella
// —hash— de cada script). En ningún caso 'unsafe-inline': un script inyectado no corre.

/**
 * @param {{ scriptSrc: string, styleSrc: string, sentry?: string | null }} options
 * @returns {string}
 */
export function buildPolicy({ scriptSrc, styleSrc, sentry = null }) {
  return [
    "default-src 'self'",
    `script-src ${scriptSrc}`,
    `style-src ${styleSrc}`,
    "img-src 'self' blob: data:",
    // Notas de voz: se escuchan antes de mandar (blob:) y después desde la API ('self').
    "media-src 'self' blob:",
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

/**
 * Para una página armada de antemano: solo corren los scripts de la app ('self') y los que Next
 * escribió dentro de la página, identificados por su huella exacta.
 * @param {string[]} hashes  'sha256-…' de cada <script> sin src
 * @param {string | null} [sentry]
 */
export function hashPolicy(hashes, sentry = null) {
  const allowed = [...new Set(hashes)].map((h) => `'${h}'`).join(" ");
  return buildPolicy({ scriptSrc: `'self'${allowed ? ` ${allowed}` : ""}`, styleSrc: "'self'", sentry });
}
