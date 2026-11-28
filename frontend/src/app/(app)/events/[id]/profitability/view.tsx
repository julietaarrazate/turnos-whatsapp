"use client";

import { EventProfitability } from "@/features/events/event-profitability";
import { useSegment } from "@/lib/route-params";

export function View() {
  return <EventProfitability id={useSegment(1)} />;
}
