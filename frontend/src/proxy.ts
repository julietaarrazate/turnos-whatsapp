import { NextResponse, type NextRequest } from "next/server";

/**
 * Chequeo optimista: sin la cookie indicadora de sesión, se manda a /login sin cargar la app.
 * NO es autorización: el backend valida cada request (ver ARCHITECTURE §8).
 */
export function proxy(request: NextRequest) {
  if (request.cookies.has("has_session")) return NextResponse.next();
  const url = request.nextUrl.clone();
  url.pathname = "/login";
  url.search = `?next=${encodeURIComponent(request.nextUrl.pathname + request.nextUrl.search)}`;
  return NextResponse.redirect(url);
}

export const config = {
  // Todo excepto: API, estáticos, PWA, páginas públicas de auth, la offline y las propuestas (/p/).
  matcher: [
    "/((?!api|_next/static|_next/image|favicon.ico|icons|sw.js|manifest.webmanifest|apple-icon.png|login|invite|reset-password|offline|p/).*)",
  ],
};
