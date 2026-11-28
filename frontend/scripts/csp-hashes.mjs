// Entre los dos `next build`: junta la huella (hash sha256) de cada script que Next escribió dentro
// de las páginas armadas de antemano y la guarda en .csp-hashes.json. El segundo armado la sirve
// como CSP (next.config.ts). Así las páginas son estáticas —abren al instante— y aun así un script
// inyectado no corre: no tiene la huella.
import { createHash } from "node:crypto";
import { existsSync, readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const INLINE = /<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g;

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
  // Las páginas armadas de antemano: en .next/server/app (local) o en el caché de rutas (Vercel).
  const hashes = new Set();
  let pages = 0;
  for (const html of htmlFiles(join(process.cwd(), ".next", "server"))) {
    for (const hash of inlineHashes(readFileSync(html, "utf8"))) hashes.add(hash);
    pages++;
  }
  if (pages === 0) throw new Error("No encontré páginas armadas de antemano en .next/server");
  const file = join(process.cwd(), ".csp-hashes.json");
  const found = [...hashes].sort();
  if (process.argv.includes("--check")) {
    // Después del segundo armado: la CSP que quedó servida tiene que cubrir cada script.
    const served = new Set(existsSync(file) ? JSON.parse(readFileSync(file, "utf8")) : []);
    const missing = found.filter((h) => !served.has(h));
    if (missing.length > 0) {
      throw new Error(`La CSP no cubre ${missing.length} scripts del segundo armado: cambiaron entre armados`);
    }
    console.log(`CSP verificada: cubre los ${found.length} scripts de ${pages} páginas`);
  } else {
    writeFileSync(file, JSON.stringify(found, null, 2));
    console.log(`CSP: ${found.length} huellas de ${pages} páginas armadas de antemano`);
  }
}
