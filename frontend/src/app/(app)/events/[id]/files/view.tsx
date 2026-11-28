"use client";

import { EventFiles } from "@/features/files/event-files";
import { useSegment } from "@/lib/route-params";

export function View() {
  return <EventFiles eventId={useSegment(1)} />;
}
