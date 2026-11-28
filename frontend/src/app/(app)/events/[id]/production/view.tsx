"use client";

import { EventProduction } from "@/features/events/event-production";
import { useSegment } from "@/lib/route-params";

export function View() {
  return <EventProduction id={useSegment(1)} />;
}
