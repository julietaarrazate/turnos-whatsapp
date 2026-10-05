"use client";

import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import type { MarkupResolution, MarkupRule } from "@/lib/api/types";
import { formatPercent } from "@/lib/format/number";

export const PRICING_KEY = ["pricing"] as const;

export function useMarkupRules(enabled = true) {
  return useQuery({
    queryKey: [...PRICING_KEY, "rules"],
    queryFn: async () => unwrap(await api.GET("/api/v1/pricing/markup-rules")),
    enabled,
  });
}

/** "30 %" o "20 % de margen (markup 25 %)". */
export function ruleLabel(rule: Pick<MarkupRule, "mode" | "value" | "effective_markup">): string {
  if (rule.mode === "MARGIN") {
    return `${pct(rule.value)} de margen (markup ${pct(rule.effective_markup)})`;
  }
  return pct(rule.value);
}

export function pct(fraction: string): string {
  // Sin ceros decimales de más: "30,00 %" → "30 %", "3,50 %" → "3,5 %".
  return formatPercent(fraction, 2).replace(/,?0+ %$/, " %");
}

const SOURCE_LABELS: Record<MarkupResolution["source"], string> = {
  LINE: "manual en la línea",
  VERSION: "del presupuesto",
  CLIENT: "cliente",
  PRODUCT: "producto",
  CATEGORY: "rubro",
  ORG: "markup general",
  TARGET_MARGIN: "margen objetivo",
  TARGET_PRICE: "precio objetivo",
};

/** "40 % · rubro Estructura" (DOMAIN_MODEL §5.3: el valor y su origen). */
export function resolutionLabel(resolution: MarkupResolution): string {
  const origin = resolution.source_name
    ? `${SOURCE_LABELS[resolution.source]} ${resolution.source_name}`
    : SOURCE_LABELS[resolution.source];
  return `${pct(resolution.markup)} · ${origin}`;
}

/** "0.300000" y "0.3" son el mismo valor (comparación de strings, sin floats). */
export function sameFraction(a: string | null, b: string | null): boolean {
  const norm = (x: string | null) => (x === null ? null : x.includes(".") ? x.replace(/0+$/, "").replace(/\.$/, "") : x);
  return norm(a) === norm(b);
}
