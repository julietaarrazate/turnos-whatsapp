"use client";

import { EventShell } from "@/features/events/event-detail";
import { useSegment } from "@/lib/route-params";

export function LayoutView({ children }: { children: React.ReactNode }) {
  return <EventShell id={useSegment(1)}>{children}</EventShell>;
}
