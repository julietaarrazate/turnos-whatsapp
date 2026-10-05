import "server-only";

import { headers } from "next/headers";
import { cache } from "react";

import type { PublicProposal } from "@/lib/api/types";

const API_ORIGIN = process.env.API_ORIGIN ?? "http://localhost:8000";

export type PublicResult =
  | { kind: "ok"; data: PublicProposal }
  | { kind: "missing" }
  | { kind: "revoked" };

/**
 * Una sola lectura por request (la comparten generateMetadata y la página: cada lectura cuenta
 * como una vista). Reenvía el user-agent para que el backend no cuente los robots de vista previa.
 */
export const getPublicProposal = cache(async (token: string): Promise<PublicResult> => {
  const incoming = await headers();
  const response = await fetch(`${API_ORIGIN}/api/v1/public/proposals/${encodeURIComponent(token)}`, {
    cache: "no-store",
    headers: {
      "user-agent": incoming.get("user-agent") ?? "",
      "x-forwarded-for": incoming.get("x-forwarded-for") ?? "",
    },
  });
  if (response.status === 404 || response.status === 422) return { kind: "missing" };
  if (response.status === 410) return { kind: "revoked" };
  if (!response.ok) throw new Error(`No se pudo cargar la propuesta (${response.status})`);
  return { kind: "ok", data: (await response.json()) as PublicProposal };
});
