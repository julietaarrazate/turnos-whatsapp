import * as Sentry from "@sentry/nextjs";

import { SENTRY_DATA_COLLECTION, redactTokens } from "@/lib/observability";

// Solo se activa si hay DSN (staging/producción).
const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;

if (dsn) {
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
}

export const onRouterTransitionStart = dsn ? Sentry.captureRouterTransitionStart : undefined;
