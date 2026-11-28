"use client";

import { EventExpenses } from "@/features/events/event-expenses";
import { useSegment } from "@/lib/route-params";

export function View() {
  return <EventExpenses id={useSegment(1)} />;
}
