"use client";

import { useSearchParams } from "next/navigation";

import { CompareVersions } from "@/features/budgets/compare-versions";
import { useSegment } from "@/lib/route-params";

export function View() {
  const query = useSearchParams();
  const from = Number(query.get("from")) || 1;
  const to = Number(query.get("to")) || from + 1;
  return <CompareVersions budgetId={useSegment(1)} from={from} to={to} />;
}
