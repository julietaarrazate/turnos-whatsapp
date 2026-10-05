"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Notice } from "@/components/ui/notice";
import { useSession } from "@/features/auth/session";
import { api, errorMessage, unwrap } from "@/lib/api/client";

import { PercentField } from "./percent-input";
import { PRICING_KEY, resolutionLabel, ruleLabel, sameFraction, useMarkupRules } from "./shared";

/**
 * Markup propio de un producto o de un cliente. Muestra el que aplica hoy (y de dónde sale) y,
 * con `pricing.settings`, permite fijar uno propio o volver a la regla general.
 */
export function ScopedMarkup({ scope, scopeId }: { scope: "PRODUCT" | "CLIENT"; scopeId: string }) {
  const { can } = useSession();
  const queryClient = useQueryClient();
  const visible = can("margin.view");
  const editable = can("pricing.settings");
  const rules = useMarkupRules(visible);
  const resolution = useQuery({
    queryKey: [...PRICING_KEY, "resolve", scopeId],
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/pricing/resolve", { params: { query: { product_id: scopeId } } })),
    enabled: visible && scope === "PRODUCT",
  });
  const rule = rules.data?.find((r) => r.scope === scope && r.scope_id === scopeId);
  const [value, setValue] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);
  const [valid, setValid] = useState(true);
  const refresh = () => {
    setTouched(false);
    return queryClient.invalidateQueries({ queryKey: PRICING_KEY });
  };
  const save = useMutation({
    mutationFn: async (fraction: string) =>
      unwrap(
        await api.PUT("/api/v1/pricing/markup-rules", {
          body: { scope, scope_id: scopeId, mode: "MARKUP", value: fraction },
        }),
      ),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: async (id: string) =>
      unwrap(await api.DELETE("/api/v1/pricing/markup-rules/{rule_id}", { params: { path: { rule_id: id } } })),
    onSuccess: refresh,
  });

  if (!visible || rules.isPending) return null;
  const current =
    scope === "PRODUCT"
      ? resolution.data
        ? `Al presupuestar toma ${resolutionLabel(resolution.data)}.`
        : null
      : rule
        ? `Markup preferencial: ${ruleLabel(rule)}. Pisa al del producto y del rubro.`
        : "Usa los markups de cada producto y rubro.";

  return (
    <section className="mb-4 rounded-xl border border-line bg-surface p-5">
      <h2 className="font-semibold">Markup</h2>
      {current ? <p className="mt-1 text-sm text-ink-muted">{current}</p> : null}
      {editable ? (
        <form
          aria-label="Markup propio"
          className="mt-4 flex flex-wrap items-start gap-3"
          onSubmit={(event) => {
            event.preventDefault();
            if (value === null && rule) remove.mutate(rule.id);
            else if (value !== null) save.mutate(value);
          }}
        >
          <div className="w-40">
            <PercentField
              key={rule?.updated_at ?? "none"}
              label={scope === "PRODUCT" ? "Markup propio" : "Markup preferencial"}
              initial={rule && rule.mode === "MARKUP" ? rule.value : null}
              placeholder="—"
              hint="Vacío = sin regla propia"
              onValue={(v, ok) => {
                setValue(v);
                setValid(ok);
                setTouched(true);
              }}
            />
          </div>
          <div className="pt-6">
            <Button
              type="submit"
              variant="secondary"
              loading={save.isPending || remove.isPending}
              disabled={!touched || !valid || sameFraction(value, rule?.value ?? null)}
            >
              Guardar
            </Button>
          </div>
          {save.isError || remove.isError ? (
            <div className="w-full">
              <Notice tone="error">{errorMessage(save.error ?? remove.error)}</Notice>
            </div>
          ) : null}
        </form>
      ) : null}
    </section>
  );
}
