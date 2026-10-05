import * as Sentry from "@sentry/nextjs";

import { SENTRY_DATA_COLLECTION, redactTokens } from "@/lib/observability";

export async function register() {
  const dsn = process.env.SENTRY_DSN;
  if (!dsn) return;
  Sentry.init({
    dsn,
    environment: process.env.APP_ENV ?? "production",
    release: process.env.VERCEL_GIT_COMMIT_SHA,
    dataCollection: { ...SENTRY_DATA_COLLECTION, httpBodies: [] },
    tracesSampleRate: 0.1,
    beforeSend(event) {
      if (event.request?.url) event.request.url = redactTokens(event.request.url);
      if (event.transaction) event.transaction = redactTokens(event.transaction);
      return event;
    },
  });
}

export const onRequestError = Sentry.captureRequestError;
