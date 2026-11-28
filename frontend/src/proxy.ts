import { NextResponse, type NextRequest } from "next/server";

import { contentSecurityPolicy } from "@/lib/csp";

/** Páginas que se ven sin sesión: auth, la offline de la PWA y la propuesta pública. */
const PUBLIC = /^\/(login|invite|reset-password|offline|p|a)(\/|$)/;

/** Las únicas páginas que se arman en el momento (leen datos del servidor al armarse). El resto
 * se arma de antemano y trae su CSP con la huella de cada script (scripts/csp-hashes.mjs). */
const RENDERED_ON_REQUEST = /^\/(p|a|invite|reset-password)\/[^/]+$/;

export function rendersOnRequest(pathname: string): boolean {
  return RENDERED_ON_REQUEST.test(pathname);
}

/** Lectores de vistas previas (WhatsApp, Facebook, Telegram...): arman la miniatura del link. */
const PREVIEW_BOTS = /WhatsApp|facebookexternalhit|Facebot|Twitterbot|TelegramBot|Slackbot|LinkedInBot|Discordbot|SkypeUriPreview|Applebot|Googlebot|bingbot/i;

export function isPreviewBot(userAgent: string | null): boolean {
  return !!userAgent && PREVIEW_BOTS.test(userAgent);
}

/**
 * 1. Chequeo optimista de sesión: sin la cookie indicadora, a /login sin cargar la app.
 *    NO es autorización: el backend valida cada request (ver ARCHITECTURE §8).
 * 2. CSP (ARCHITECTURE §8.3): las páginas que se arman en el momento llevan un nonce nuevo por
 *    request (Next se lo pone a sus scripts). Las armadas de antemano no pasan por acá: su CSP con
 *    huellas ya viene con la página.
 */
export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const needsLogin = !PUBLIC.test(pathname) && !request.cookies.has("has_session");
  // WhatsApp no siempre sigue la redirección al armar la miniatura: al lector de vistas previas
  // se le sirve la página de ingreso en la misma dirección (trae el título y la imagen de Handie).
  const preview = needsLogin && isPreviewBot(request.headers.get("user-agent"));
  if (needsLogin && !preview) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.search = `?next=${encodeURIComponent(pathname + search)}`;
    return NextResponse.redirect(url);
  }

  if (!rendersOnRequest(pathname)) {
    return preview ? NextResponse.rewrite(new URL("/login", request.url)) : NextResponse.next();
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
