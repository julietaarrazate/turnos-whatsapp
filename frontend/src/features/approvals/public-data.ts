import "server-only";

import { headers } from "next/headers";
import { cache } from "react";

import type { PublicApproval } from "@/lib/api/types";

const API_ORIGIN = process.env.API_ORIGIN ?? "http://localhost:8000";

export type ApprovalResult = { kind: "ok"; data: PublicApproval } | { kind: "missing" };

/** Una sola lectura por request (la comparten generateMetadata y la página). */
export const getPublicApproval = cache(async (token: string): Promise<ApprovalResult> => {
  const incoming = await headers();
  const response = await fetch(`${API_ORIGIN}/api/v1/public/approvals/${encodeURIComponent(token)}`, {
    cache: "no-store",
    headers: {
      "user-agent": incoming.get("user-agent") ?? "",
      "x-forwarded-for": incoming.get("x-forwarded-for") ?? "",
    },
  });
  if (response.status === 404 || response.status === 422) return { kind: "missing" };
  if (!response.ok) throw new Error(`No se pudo cargar el diseño (${response.status})`);
  return { kind: "ok", data: (await response.json()) as PublicApproval };
});
