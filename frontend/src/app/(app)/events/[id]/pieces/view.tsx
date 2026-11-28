"use client";

import { EventPieces } from "@/features/events/event-pieces";
import { useSegment } from "@/lib/route-params";

export function View() {
  return <EventPieces id={useSegment(1)} />;
}
