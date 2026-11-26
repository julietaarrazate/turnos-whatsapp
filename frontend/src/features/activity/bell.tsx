"use client";

import { useQuery } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import Link from "next/link";

import { api, unwrap } from "@/lib/api/client";
import { cn } from "@/lib/cn";
import { LIVE } from "@/lib/live";

export const UNREAD_KEY = ["activity", "unread"] as const;

export function useUnread() {
  return useQuery({
    ...LIVE,
    queryKey: UNREAD_KEY,
    queryFn: async () => unwrap(await api.GET("/api/v1/activity/unread")),
  });
}

export function bellLabel(count: number): string {
  if (count === 0) return "Novedades: ninguna nueva";
  return `Novedades: ${count > 98 ? "más de 99" : count} ${count === 1 ? "nueva" : "nuevas"}`;
}

/** La campanita: cuántos movimientos de otros hay desde la última vez que se abrió Actividad. */
export function ActivityBell({ tone = "onBrand" }: { tone?: "onBrand" | "onSurface" }) {
  const unread = useUnread();
  const count = unread.data?.count ?? 0;
  return (
    <Link
      href="/activity"
      aria-label={bellLabel(count)}
      className={cn(
        "relative flex size-11 shrink-0 items-center justify-center rounded-full",
        tone === "onBrand" ? "bg-white/15 text-white" : "text-ink-muted hover:bg-subtle hover:text-ink",
      )}
    >
      <Bell className="size-5" aria-hidden />
      {count ? (
        <span className="absolute top-1 right-1 flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-magenta px-1 text-[11px] font-bold text-white">
          {count > 98 ? "99+" : count}
        </span>
      ) : null}
    </Link>
  );
}
