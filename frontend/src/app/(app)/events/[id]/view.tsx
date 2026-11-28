"use client";

import { EventSummary } from "@/features/events/event-detail";
import { useSegment } from "@/lib/route-params";

export function View() {
  return <EventSummary id={useSegment(1)} />;
}
