"use client";

import { PieceDetail } from "@/features/events/event-pieces";
import { useSegment } from "@/lib/route-params";

export function View() {
  return <PieceDetail eventId={useSegment(1)} pieceId={useSegment(3)} />;
}
