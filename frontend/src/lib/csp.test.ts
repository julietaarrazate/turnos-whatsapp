import { describe, expect, it } from "vitest";

import { contentSecurityPolicy, sentryOrigin } from "./csp";

const directives = (csp: string) => new Map(csp.split("; ").map((d) => [d.split(" ")[0], d] as const));

describe("contentSecurityPolicy", () => {
  it("en producción solo deja scripts y estilos con el nonce, sin inline ni eval", () => {
    const d = directives(contentSecurityPolicy("abc", false, null));
    expect(d.get("script-src")).toBe("script-src 'self' 'nonce-abc' 'strict-dynamic'");
    expect(d.get("style-src")).toBe("style-src 'self' 'nonce-abc'");
    expect(d.get("object-src")).toBe("object-src 'none'");
    expect(d.get("frame-ancestors")).toBe("frame-ancestors 'none'");
    expect(d.get("connect-src")).toBe("connect-src 'self'");
  });

  it("en desarrollo agrega lo que necesita React (eval y estilos inline)", () => {
    const d = directives(contentSecurityPolicy("abc", true, null));
    expect(d.get("script-src")).toContain("'unsafe-eval'");
    expect(d.get("style-src")).toBe("style-src 'self' 'unsafe-inline'");
  });

  it("con Sentry permite conectarse solo al origen del DSN", () => {
    const d = directives(contentSecurityPolicy("abc", false, "https://o1.ingest.sentry.io"));
    expect(d.get("connect-src")).toBe("connect-src 'self' https://o1.ingest.sentry.io");
  });
});

describe("sentryOrigin", () => {
  it.each([
    ["https://key@o1.ingest.sentry.io/123", "https://o1.ingest.sentry.io"],
    ["no-es-una-url", null],
    ["", null],
  ])("%s → %s", (dsn, expected) => {
    expect(sentryOrigin(dsn)).toBe(expected);
  });
});
