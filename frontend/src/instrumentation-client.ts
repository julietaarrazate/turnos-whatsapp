import { SENTRY_DATA_COLLECTION, redactTokens } from "@/lib/observability";

// Solo se activa si hay DSN (staging/producción).
const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;

type SentryModule = typeof import("@sentry/nextjs");
let sentry: SentryModule | undefined;

if (dsn) {
  // Import dinámico: el SDK (~80 KB gzip) iba en el bundle de TODAS las páginas aunque no hubiera
  // DSN. Ahora sin DSN no se descarga, y con DSN se carga aparte sin frenar la primera pintura.
  void import("@sentry/nextjs").then((Sentry) => {
    Sentry.init({
      dsn,
      environment: process.env.NEXT_PUBLIC_APP_ENV ?? "production",
      release: process.env.NEXT_PUBLIC_RELEASE,
      dataCollection: { ...SENTRY_DATA_COLLECTION, httpBodies: [] },
      tracesSampleRate: 0.1,
      beforeSend(event) {
        if (event.request?.url) event.request.url = redactTokens(event.request.url);
        if (event.transaction) event.transaction = redactTokens(event.transaction);
        return event;
      },
      beforeSendTransaction(event) {
        if (event.transaction) event.transaction = redactTokens(event.transaction);
        if (event.request?.url) event.request.url = redactTokens(event.request.url);
        return event;
      },
    });
    sentry = Sentry;
  });
}

export const onRouterTransitionStart: SentryModule["captureRouterTransitionStart"] | undefined = dsn
  ? (...args) => sentry?.captureRouterTransitionStart(...args)
  : undefined;
