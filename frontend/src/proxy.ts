import { NextResponse, type NextRequest } from "next/server";

import { contentSecurityPolicy } from "@/lib/csp";

/** Páginas que se ven sin sesión: auth, la offline de la PWA y la propuesta pública. */
const PUBLIC = /^\/(login|invite|reset-password|offline|p)(\/|$)/;

/**
 * 1. CSP estricta con nonce por request (ARCHITECTURE §8.3): Next lo toma del header del request
 *    y se lo pone a sus scripts. Por eso todas las páginas se renderizan por request (layout raíz).
 * 2. Chequeo optimista de sesión: sin la cookie indicadora, a /login sin cargar la app.
 *    NO es autorización: el backend valida cada request (ver ARCHITECTURE §8).
 */
export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  if (!PUBLIC.test(pathname) && !request.cookies.has("has_session")) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.search = `?next=${encodeURIComponent(pathname + search)}`;
    return NextResponse.redirect(url);
  }

  const nonce = btoa(crypto.randomUUID());
  const csp = contentSecurityPolicy(nonce, process.env.NODE_ENV === "development");
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", csp);
  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", csp);
  return response;
}

export const config = {
  // Todo menos el API (lo atiende el backend) y los archivos estáticos.
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|icons|sw.js|manifest.webmanifest|apple-icon.png|icon.svg|opengraph-image|twitter-image).*)"],
};
