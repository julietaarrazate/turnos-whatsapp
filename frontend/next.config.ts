import type { NextConfig } from "next";

// El browser llama a /api/* en el MISMO origen y Next lo reenvía al backend (D-13): cookies
// first-party, sin CORS, y los previews funcionan sin configurar dominios.
const API_ORIGIN = process.env.API_ORIGIN ?? "http://localhost:8000";

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(self), microphone=(self), geolocation=()" },
];

const nextConfig: NextConfig = {
  poweredByHeader: false,
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
