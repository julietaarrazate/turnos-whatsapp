import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

import type { NextConfig } from "next";

import { hashPolicy } from "./src/lib/csp-policy.mjs";

// El browser llama a /api/* en el MISMO origen y Next lo reenvía al backend (D-13): cookies
// first-party, sin CORS, y los previews funcionan sin configurar dominios.
const API_ORIGIN = process.env.API_ORIGIN ?? "http://localhost:8000";

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(self), microphone=(self), geolocation=()" },
];

// CSP de las páginas armadas de antemano: la huella (sha256) de cada script que Next escribe dentro
// de esas páginas. La calcula scripts/csp-hashes.mjs después de un primer armado y el segundo
// armado la sirve como encabezado (ver "build" en package.json). Las páginas que se arman en el
// momento (/p, /a, invitación, reset) no la llevan: usan nonce desde src/proxy.ts.
const HASHES_FILE = join(process.cwd(), ".csp-hashes.json");
const pageHashes: string[] =
  process.env.NODE_ENV === "production" && existsSync(HASHES_FILE) ? JSON.parse(readFileSync(HASHES_FILE, "utf8")) : [];
const sentry = (() => {
  try {
    return process.env.NEXT_PUBLIC_SENTRY_DSN ? new URL(process.env.NEXT_PUBLIC_SENTRY_DSN).origin : null;
  } catch {
    return null;
  }
})();

const nextConfig: NextConfig = {
  poweredByHeader: false,
  // Mismo ID en los dos armados: si no, cambia el contenido de los scripts y sus huellas.
  generateBuildId: async () => process.env.VERCEL_GIT_COMMIT_SHA ?? process.env.GITHUB_SHA ?? "local",
  async rewrites() {
    return {
      // Las pantallas con ID se arman una sola vez como plantilla (`_`) y la pantalla lee el ID
      // real de la dirección (src/lib/route-params.ts): abren al instante, sin pasar por el
      // servidor de Vercel. "new", "import"… son pantallas propias, no IDs.
      beforeFiles: [
        { source: "/events/:id((?!_$)[^/]+)", destination: "/events/_" },
        { source: "/events/:id((?!_$)[^/]+)/pieces/:piece((?!_$)[^/]+)", destination: "/events/_/pieces/_" },
        { source: "/events/:id((?!_$)[^/]+)/:tab(budgets|expenses|files|pieces|production|profitability)", destination: "/events/_/:tab" },
        { source: "/budgets/:id((?!_$|new$)[^/]+)", destination: "/budgets/_" },
        { source: "/budgets/:id((?!_$|new$)[^/]+)/compare", destination: "/budgets/_/compare" },
        { source: "/catalog/:id((?!_$|new$|import$|bulk-increase$|packages$)[^/]+)", destination: "/catalog/_" },
        { source: "/clients/:id((?!_$|new$)[^/]+)", destination: "/clients/_" },
        { source: "/suppliers/:id((?!_$|new$)[^/]+)", destination: "/suppliers/_" },
      ],
      afterFiles: [{ source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` }],
      fallback: [],
    };
  },
  async headers() {
    return [
      { source: "/(.*)", headers: securityHeaders },
      ...(pageHashes.length > 0
        ? [
            {
              // Todo menos el API y las páginas que se arman en el momento (esas llevan nonce).
              source: "/((?!api/|p/|a/|invite/|reset-password/[^/]+$).*)",
              headers: [{ key: "Content-Security-Policy", value: hashPolicy(pageHashes, sentry) }],
            },
          ]
        : []),
      {
        // Propuesta pública: que el token no viaje como referrer y que no se indexe.
        source: "/p/:token*",
        headers: [
          { key: "Referrer-Policy", value: "no-referrer" },
          { key: "X-Robots-Tag", value: "noindex, nofollow" },
          { key: "Cache-Control", value: "private, no-store" },
        ],
      },
      {
        source: "/sw.js",
        headers: [
          { key: "Content-Type", value: "application/javascript; charset=utf-8" },
          { key: "Cache-Control", value: "no-cache, no-store, must-revalidate" },
          { key: "Content-Security-Policy", value: "default-src 'self'; script-src 'self'" },
        ],
      },
    ];
  },
};

export default nextConfig;
