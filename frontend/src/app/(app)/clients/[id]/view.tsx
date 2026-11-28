"use client";

import { ClientDetail } from "@/features/clients/client-form";
import { useSegment } from "@/lib/route-params";

export function View() {
  return <ClientDetail id={useSegment(1)} />;
}
