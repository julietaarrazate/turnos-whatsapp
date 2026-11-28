"use client";

import { EventBudgets } from "@/features/events/event-detail";
import { useSegment } from "@/lib/route-params";

export function View() {
  return <EventBudgets id={useSegment(1)} />;
}
