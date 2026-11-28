"use client";

import { useSearchParams } from "next/navigation";

import { BudgetEditor } from "@/features/budgets/budget-editor";
import { useSegment } from "@/lib/route-params";

export function View() {
  const query = useSearchParams();
  // Después de "Duplicar": cuántos costos y markups cambiaron respecto del original.
  const costs = query.get("costos");
  const rules = query.get("reglas");
  const copied = costs !== null && rules !== null ? { costs: Number(costs) || 0, rules: Number(rules) || 0 } : undefined;
  return <BudgetEditor budgetId={useSegment(1)} copied={copied} />;
}
