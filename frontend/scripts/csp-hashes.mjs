// Después de `next build`: a cada página armada de antemano le pone su CSP con la huella (hash
// sha256) de cada script que Next escribió dentro del HTML. La CSP viaja como encabezado de la
// página (el archivo .meta que Next sirve junto al .html). Así la página es estática —abre al
// instante— y aun así un script inyectado no corre: no tiene la huella.
import { createHash } from "node:crypto";
import { readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { hashPolicy } from "../src/lib/csp-policy.mjs";

const APP = join(process.cwd(), ".next", "server", "app");
const INLINE = /<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g;

function sentryOrigin() {
  try {
    return process.env.NEXT_PUBLIC_SENTRY_DSN ? new URL(process.env.NEXT_PUBLIC_SENTRY_DSN).origin : null;
  } catch {
    return null;
  }
}

/** Las huellas de los scripts escritos dentro de un HTML. */
export function inlineHashes(html) {
  return [...html.matchAll(INLINE)]
    .map((m) => m[1])
    .filter((body) => body.length > 0)
    .map((body) => `sha256-${createHash("sha256").update(body, "utf8").digest("base64")}`);
}

function* htmlFiles(dir) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) yield* htmlFiles(path);
    else if (name.endsWith(".html")) yield path;
  }
}

if (process.argv[1]?.endsWith("csp-hashes.mjs")) {
  const sentry = sentryOrigin();
  let pages = 0;
  for (const html of htmlFiles(APP)) {
    const metaPath = html.replace(/\.html$/, ".meta");
    let meta;
    try {
      meta = JSON.parse(readFileSync(metaPath, "utf8"));
    } catch {
      meta = {};
    }
    meta.headers = { ...meta.headers, "content-security-policy": hashPolicy(inlineHashes(readFileSync(html, "utf8")), sentry) };
    writeFileSync(metaPath, JSON.stringify(meta, null, 2));
    pages++;
  }
  if (pages === 0) throw new Error("No encontré páginas armadas de antemano en .next/server/app");
  console.log(`CSP con huellas en ${pages} páginas armadas de antemano`);
}
