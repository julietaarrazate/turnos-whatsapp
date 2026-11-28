import { describe, expect, it } from "vitest";

import { rendersOnRequest } from "@/proxy";

import { contentSecurityPolicy, sentryOrigin } from "./csp";
import { hashPolicy } from "./csp-policy.mjs";

const directives = (csp: string) => new Map(csp.split("; ").map((d) => [d.split(" ")[0], d] as const));

describe("contentSecurityPolicy", () => {
  it("en producción solo deja scripts y estilos con el nonce, sin inline ni eval", () => {
    const d = directives(contentSecurityPolicy("abc", false, null));
    expect(d.get("script-src")).toBe("script-src 'self' 'nonce-abc' 'strict-dynamic'");
    expect(d.get("style-src")).toBe("style-src 'self' 'nonce-abc'");
    expect(d.get("object-src")).toBe("object-src 'none'");
    expect(d.get("frame-ancestors")).toBe("frame-ancestors 'none'");
    expect(d.get("connect-src")).toBe("connect-src 'self'");
    expect(d.get("media-src")).toBe("media-src 'self' blob:");
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

describe("hashPolicy (páginas armadas de antemano)", () => {
  it("solo deja los scripts de la app y los de la página por su huella, sin inline", () => {
    const d = directives(hashPolicy(["sha256-AAA=", "sha256-BBB=", "sha256-AAA="]));
    expect(d.get("script-src")).toBe("script-src 'self' 'sha256-AAA=' 'sha256-BBB='");
    expect(d.get("style-src")).toBe("style-src 'self'");
    expect(d.get("frame-ancestors")).toBe("frame-ancestors 'none'");
  });
});

describe("qué páginas se arman en el momento", () => {
  it.each([
    ["/p/abc", true],
    ["/a/abc", true],
    ["/invite/abc", true],
    ["/reset-password/abc", true],
    ["/reset-password", false],
    ["/events/123", false],
    ["/login", false],
  ])("%s → %s", (path, expected) => {
    expect(rendersOnRequest(path)).toBe(expected);
  });
});
