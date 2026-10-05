"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { CheckboxField, SelectField, TextField } from "@/components/ui/field";
import { Notice } from "@/components/ui/notice";
import { PageHeader } from "@/components/ui/page-header";
import { Switch } from "@/components/ui/switch";
import { useSession } from "@/features/auth/session";
import { categoryTree } from "@/features/catalog/category-tree";
import { useCategories } from "@/features/catalog/shared";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import type { MarkupRule, PricingSettings, SaleCharge, Schemas } from "@/lib/api/types";
import { formatDay, todayInArgentina } from "@/lib/format/date";
import { formatMoney } from "@/lib/format/number";
import { parseDecimalAR } from "@/lib/parse/number";

import { PercentField } from "./percent-input";
import { PRICING_KEY, pct, ruleLabel, sameFraction, useMarkupRules } from "./shared";

function Section({ title, description, children }: { title: string; description?: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-line bg-surface p-5">
      <h2 className="font-semibold">{title}</h2>
      {description ? <p className="mt-1 text-sm text-ink-muted">{description}</p> : null}
      <div className="mt-4">{children}</div>
    </section>
  );
}

function useSaveRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: Schemas["MarkupRuleIn"]) => unwrap(await api.PUT("/api/v1/pricing/markup-rules", { body })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: PRICING_KEY }),
  });
}

function useDeleteRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) =>
      unwrap(await api.DELETE("/api/v1/pricing/markup-rules/{rule_id}", { params: { path: { rule_id: id } } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: PRICING_KEY }),
  });
}

// --- Markup general y por rubro ----------------------------------------------------------

function GeneralMarkup({ rule, editable }: { rule: MarkupRule; editable: boolean }) {
  const save = useSaveRule();
  const [value, setValue] = useState<string | null>(rule.value);
  const [valid, setValid] = useState(true);
  const [mode, setMode] = useState(rule.mode);
  return (
    <form
      className="grid gap-3 sm:grid-cols-[10rem_14rem_auto] sm:items-start"
      onSubmit={(event) => {
        event.preventDefault();
        if (value !== null && valid) save.mutate({ scope: "ORG", mode, value });
      }}
    >
      <PercentField
        label={mode === "MARGIN" ? "Margen" : "Markup"}
        initial={rule.value}
        disabled={!editable}
        onValue={(v, ok) => {
          setValue(v);
          setValid(ok);
        }}
      />
      <SelectField
        label="Se expresa como"
        value={mode}
        disabled={!editable}
        onChange={(e) => setMode(e.target.value as MarkupRule["mode"])}
        options={[
          { value: "MARKUP", label: "Markup sobre el costo" },
          { value: "MARGIN", label: "Margen sobre la venta" },
        ]}
      />
      {editable ? (
        <div className="sm:pt-6">
          <Button type="submit" loading={save.isPending} disabled={value === null || !valid}>
            Guardar
          </Button>
        </div>
      ) : null}
      <p className="text-sm text-ink-muted sm:col-span-3">Hoy: {ruleLabel(rule)}.</p>
      {save.isError ? (
        <div className="sm:col-span-3">
          <Notice tone="error">{errorMessage(save.error)}</Notice>
        </div>
      ) : null}
    </form>
  );
}

function CategoryRuleRow({
  categoryId,
  name,
  depth,
  rule,
  editable,
  fallback,
}: {
  categoryId: string;
  name: string;
  depth: number;
  rule: MarkupRule | undefined;
  editable: boolean;
  fallback: string;
}) {
  const save = useSaveRule();
  const remove = useDeleteRule();
  const [value, setValue] = useState<string | null>(rule?.value ?? null);
  const [valid, setValid] = useState(true);
  const dirty = !sameFraction(value, rule?.value ?? null);
  return (
    <li className="flex flex-wrap items-center gap-3 py-3" style={{ paddingLeft: depth * 20 }}>
      <div className="min-w-40 flex-1">
        <p className="font-medium">{name}</p>
        <p className="text-sm text-ink-muted">{rule ? ruleLabel(rule) : `Usa ${fallback}`}</p>
      </div>
      {editable ? (
        <>
          <div className="w-28">
            <PercentField
              label={`Markup de ${name}`}
              hideLabel
              initial={rule && rule.mode === "MARKUP" ? rule.value : null}
              placeholder="—"
              onValue={(v, ok) => {
                setValue(v);
                setValid(ok);
              }}
            />
          </div>
          <Button
            size="sm"
            variant="secondary"
            disabled={!dirty || !valid}
            loading={save.isPending || remove.isPending}
            onClick={() => {
              if (value === null && rule) remove.mutate(rule.id);
              else if (value !== null) save.mutate({ scope: "CATEGORY", scope_id: categoryId, mode: "MARKUP", value });
            }}
          >
            Guardar
          </Button>
        </>
      ) : null}
      {save.isError || remove.isError ? (
        <p className="w-full text-sm text-danger">{errorMessage(save.error ?? remove.error)}</p>
      ) : null}
    </li>
  );
}

function CategoryMarkups({ rules, editable }: { rules: MarkupRule[]; editable: boolean }) {
  const categories = useCategories();
  const byCategory = new Map(rules.filter((r) => r.scope === "CATEGORY").map((r) => [r.scope_id, r]));
  const general = rules.find((r) => r.scope === "ORG");
  return (
    <ul className="divide-y divide-line">
      {categoryTree(categories.data ?? []).map(({ category, depth }) => {
        const parentRule = category.parent_id ? byCategory.get(category.parent_id) : undefined;
        const fallback = parentRule
          ? `el del rubro padre (${pct(parentRule.effective_markup)})`
          : `el general (${general ? pct(general.effective_markup) : "—"})`;
        return (
          <CategoryRuleRow
            key={category.id}
            categoryId={category.id}
            name={category.name}
            depth={depth}
            rule={byCategory.get(category.id)}
            editable={editable}
            fallback={fallback}
          />
        );
      })}
    </ul>
  );
}

function SpecificRules({ rules, editable }: { rules: MarkupRule[]; editable: boolean }) {
  const remove = useDeleteRule();
  const specific = rules.filter((r) => r.scope === "PRODUCT" || r.scope === "CLIENT");
  if (specific.length === 0) {
    return (
      <p className="text-sm text-ink-muted">
        No hay. Se definen desde la ficha de cada <Link href="/catalog" className="underline">producto</Link> o{" "}
        <Link href="/clients" className="underline">cliente</Link>.
      </p>
    );
  }
  return (
    <ul className="divide-y divide-line">
      {specific.map((rule) => (
        <li key={rule.id} className="flex items-center gap-3 py-3">
          <div className="min-w-0 flex-1">
            <Link
              href={rule.scope === "PRODUCT" ? `/catalog/${rule.scope_id}` : `/clients/${rule.scope_id}`}
              className="font-medium hover:underline"
            >
              {rule.scope_name ?? "(borrado)"}
            </Link>
            <p className="text-sm text-ink-muted">
              {rule.scope === "PRODUCT" ? "Producto" : "Cliente"} · {ruleLabel(rule)}
            </p>
          </div>
          {editable ? (
            <Button variant="ghost" size="sm" aria-label={`Quitar regla de ${rule.scope_name}`} onClick={() => remove.mutate(rule.id)}>
              <Trash2 className="size-4" aria-hidden />
            </Button>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

// --- Cargos sobre la venta ---------------------------------------------------------------

const CHARGE_SUGGESTIONS = [
  { name: "IIBB", hint: "Ingresos brutos: la alícuota depende de tu jurisdicción y actividad" },
  { name: "Imp. débitos y créditos", hint: "Impuesto al cheque, suele ser 0,6 % o 1,2 %" },
  { name: "Comisión comercial", hint: "Si le pagás comisión a un vendedor o agencia" },
];

function ChargeRow({ charge, editable }: { charge: SaleCharge; editable: boolean }) {
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: PRICING_KEY });
  const update = useMutation({
    mutationFn: async (body: Schemas["SaleChargeUpdate"]) =>
      unwrap(
        await api.PATCH("/api/v1/pricing/sale-charges/{charge_id}", { params: { path: { charge_id: charge.id } }, body }),
      ),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: async () =>
      unwrap(await api.DELETE("/api/v1/pricing/sale-charges/{charge_id}", { params: { path: { charge_id: charge.id } } })),
    onSuccess: refresh,
  });
  return (
    <li className="flex items-center gap-3 py-3">
      <div className="min-w-0 flex-1">
        <p className={charge.is_active ? "font-medium" : "font-medium text-ink-muted line-through"}>{charge.name}</p>
        <p className="text-sm text-ink-muted">{pct(charge.rate)} de la venta neta</p>
      </div>
      {editable ? (
        <>
          <div className="w-44">
            <Switch
              label="Activo"
              checked={charge.is_active}
              disabled={update.isPending}
              onChange={(is_active) => update.mutate({ is_active })}
            />
          </div>
          <Button
            variant="ghost"
            size="sm"
            aria-label={`Borrar ${charge.name}`}
            loading={remove.isPending}
            onClick={() => {
              if (window.confirm(`¿Borrar ${charge.name}? Los presupuestos ya hechos conservan el cargo que usaron.`)) remove.mutate();
            }}
          >
            <Trash2 className="size-4" aria-hidden />
          </Button>
        </>
      ) : null}
    </li>
  );
}

function SaleCharges({ editable }: { editable: boolean }) {
  const queryClient = useQueryClient();
  const charges = useQuery({
    queryKey: [...PRICING_KEY, "charges"],
    queryFn: async () => unwrap(await api.GET("/api/v1/pricing/sale-charges")),
  });
  const [name, setName] = useState("");
  const [rate, setRate] = useState<string | null>(null);
  const [rateKey, setRateKey] = useState(0);
  const create = useMutation({
    mutationFn: async (body: Schemas["SaleChargeIn"]) => unwrap(await api.POST("/api/v1/pricing/sale-charges", { body })),
    onSuccess: () => {
      setName("");
      setRate(null);
      setRateKey((k) => k + 1);
      void queryClient.invalidateQueries({ queryKey: PRICING_KEY });
    },
  });
  const existing = new Set(charges.data?.map((c) => c.name.toLowerCase()));
  const suggestions = CHARGE_SUGGESTIONS.filter((s) => !existing.has(s.name.toLowerCase()));

  return (
    <>
      {charges.data?.length ? (
        <ul className="mb-4 divide-y divide-line">
          {charges.data.map((charge) => (
            <ChargeRow key={charge.id} charge={charge} editable={editable} />
          ))}
        </ul>
      ) : (
        <p className="mb-4 text-sm text-ink-muted">Sin cargos: el margen se calcula sin descontar nada de la venta.</p>
      )}
      {editable ? (
        <form
          aria-label="Agregar cargo"
          className="grid gap-3 sm:grid-cols-[1fr_8rem_auto] sm:items-start"
          onSubmit={(event) => {
            event.preventDefault();
            if (rate !== null) {
              create.mutate({
                name: name.trim(),
                rate,
                is_active: true,
                applies_by_default: true,
                sort: charges.data?.length ?? 0,
              });
            }
          }}
        >
          <TextField label="Cargo" value={name} required maxLength={80} onChange={(e) => setName(e.target.value)} />
          <PercentField key={rateKey} label="Alícuota" initial={null} placeholder="3,5" onValue={(v) => setRate(v)} />
          <div className="sm:pt-6">
            <Button type="submit" loading={create.isPending} disabled={!name.trim() || rate === null}>
              Agregar
            </Button>
          </div>
          {suggestions.length ? (
            <div className="flex flex-wrap gap-2 sm:col-span-3">
              {suggestions.map((s) => (
                <button
                  key={s.name}
                  type="button"
                  title={s.hint}
                  onClick={() => setName(s.name)}
                  className="rounded-full border border-line px-3 py-1 text-sm text-ink-muted hover:bg-subtle hover:text-ink"
                >
                  + {s.name}
                </button>
              ))}
            </div>
          ) : null}
          {create.isError ? (
            <div className="sm:col-span-3">
              <Notice tone="error">{errorMessage(create.error)}</Notice>
            </div>
          ) : null}
        </form>
      ) : null}
    </>
  );
}

// --- Redondeo, margen mínimo y antigüedad -------------------------------------------------

const ROUNDING_OPTIONS = [
  { value: "0.01", label: "Al centavo" },
  { value: "1", label: "Al peso" },
  { value: "10", label: "A $ 10" },
  { value: "100", label: "A $ 100" },
  { value: "1000", label: "A $ 1.000" },
];

function GeneralSettings({ settings, editable }: { settings: PricingSettings; editable: boolean }) {
  const queryClient = useQueryClient();
  const [minMargin, setMinMargin] = useState<string | null>(settings.min_margin ?? null);
  const [minValid, setMinValid] = useState(true);
  const [saved, setSaved] = useState(false);
  const save = useMutation({
    mutationFn: async (body: Schemas["PricingSettingsUpdate"]) =>
      unwrap(await api.PATCH("/api/v1/pricing/settings", { body })),
    onSuccess: (data) => {
      queryClient.setQueryData([...PRICING_KEY, "settings"], data);
      void queryClient.invalidateQueries({ queryKey: ["products"] });
      setSaved(true);
    },
  });
  return (
    <form
      className="grid gap-4 sm:grid-cols-2"
      onSubmit={(event) => {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        setSaved(false);
        save.mutate({
          rounding_increment: String(form.get("rounding_increment")) as PricingSettings["rounding_increment"],
          min_margin: minMargin,
          margin_includes_sale_charges: form.get("margin_includes_sale_charges") === "on",
          price_staleness_days: Number(form.get("price_staleness_days")),
        });
      }}
    >
      <fieldset disabled={!editable} className="contents">
        <SelectField
          label="Redondeo de cada línea"
          name="rounding_increment"
          defaultValue={settings.rounding_increment}
          options={ROUNDING_OPTIONS}
          hint="Lo que ve el cliente siempre suma exacto."
        />
        <PercentField
          label="Margen mínimo (opcional)"
          initial={settings.min_margin ?? null}
          hint="Avisa cuando un presupuesto queda por debajo. No bloquea."
          onValue={(v, ok) => {
            setMinMargin(v);
            setMinValid(ok);
          }}
        />
        <TextField
          label="Costo desactualizado después de"
          name="price_staleness_days"
          type="number"
          min={1}
          max={365}
          defaultValue={settings.price_staleness_days}
          hint="Días desde la fecha del costo."
        />
        <CheckboxField
          label="El margen objetivo descuenta los cargos sobre la venta"
          name="margin_includes_sale_charges"
          defaultChecked={settings.margin_includes_sale_charges}
          className="sm:mt-6"
        />
      </fieldset>
      {save.isError ? (
        <div className="sm:col-span-2">
          <Notice tone="error">{errorMessage(save.error)}</Notice>
        </div>
      ) : null}
      {saved ? (
        <div className="sm:col-span-2">
          <Notice tone="success">Configuración guardada.</Notice>
        </div>
      ) : null}
      {editable ? (
        <div>
          <Button type="submit" loading={save.isPending} disabled={!minValid}>
            Guardar
          </Button>
        </div>
      ) : null}
    </form>
  );
}

// --- Tipo de cambio ----------------------------------------------------------------------

function ExchangeRates() {
  const { can } = useSession();
  const queryClient = useQueryClient();
  const rates = useQuery({
    queryKey: [...PRICING_KEY, "fx"],
    queryFn: async () => unwrap(await api.GET("/api/v1/pricing/fx-rates", { params: { query: { limit: 10 } } })),
  });
  const [raw, setRaw] = useState("");
  const parsed = parseDecimalAR(raw);
  const record = useMutation({
    mutationFn: async (body: Schemas["FxRateIn"]) => unwrap(await api.POST("/api/v1/pricing/fx-rates", { body })),
    onSuccess: () => {
      setRaw("");
      void queryClient.invalidateQueries({ queryKey: [...PRICING_KEY, "fx"] });
    },
  });
  const current = rates.data?.[0];
  return (
    <>
      <p className="mb-4 text-sm">
        {current ? (
          <>
            Vigente: <span className="font-medium">US$ 1 = {formatMoney(current.rate)}</span> del {formatDay(current.rate_date)}
            {current.days_old > 7 ? <span className="ml-2 text-warning">· hace {current.days_old} días</span> : null}
          </>
        ) : (
          <span className="text-ink-muted">Todavía no cargaste un tipo de cambio.</span>
        )}
      </p>
      {can("budget.edit") ? (
        <form
          aria-label="Cargar tipo de cambio"
          className="grid gap-3 sm:grid-cols-[10rem_10rem_auto] sm:items-start"
          onSubmit={(event) => {
            event.preventDefault();
            const form = new FormData(event.currentTarget);
            if (parsed) record.mutate({ currency: "USD", rate: parsed, rate_date: String(form.get("rate_date")) });
          }}
        >
          <TextField
            label="Pesos por dólar"
            inputMode="decimal"
            value={raw}
            placeholder="1.450,50"
            onChange={(e) => setRaw(e.target.value)}
            error={raw.trim() && parsed === null ? "No es un número válido" : undefined}
          />
          <TextField label="Fecha" name="rate_date" type="date" defaultValue={todayInArgentina()} required />
          <div className="sm:pt-6">
            <Button type="submit" loading={record.isPending} disabled={!parsed}>
              Guardar
            </Button>
          </div>
          {record.isError ? (
            <div className="sm:col-span-3">
              <Notice tone="error">{errorMessage(record.error)}</Notice>
            </div>
          ) : null}
        </form>
      ) : null}
      {rates.data && rates.data.length > 1 ? (
        <details className="mt-4 text-sm">
          <summary className="cursor-pointer text-ink-muted">Historial</summary>
          <ol className="mt-2 divide-y divide-line">
            {rates.data.map((r) => (
              <li key={r.id} className="flex gap-3 py-1.5">
                <span className="w-24 text-ink-muted">{formatDay(r.rate_date)}</span>
                <span className="tabular-nums">{formatMoney(r.rate)}</span>
                <span className="ml-auto text-xs text-ink-muted">{r.created_by_name}</span>
              </li>
            ))}
          </ol>
        </details>
      ) : null}
    </>
  );
}

export function PricingSettingsPage() {
  const { can } = useSession();
  const editable = can("pricing.settings");
  const rules = useMarkupRules();
  const settings = useQuery({
    queryKey: [...PRICING_KEY, "settings"],
    queryFn: async () => unwrap(await api.GET("/api/v1/pricing/settings")),
  });
  const general = rules.data?.find((r) => r.scope === "ORG");

  return (
    <>
      <PageHeader
        title="Pricing"
        description="Cómo se calcula el precio de venta. Los cambios valen para presupuestos nuevos: los ya hechos no se tocan."
      />
      {!editable ? (
        <div className="mb-4">
          <Notice>Solo quien es dueño o administra la organización puede cambiar esta configuración.</Notice>
        </div>
      ) : null}
      {rules.isError ? <Notice tone="error">{errorMessage(rules.error)}</Notice> : null}
      <div className="flex flex-col gap-4">
        <Section
          title="Markup general"
          description="Se usa cuando el producto, su rubro o el cliente no tienen uno propio."
        >
          {general ? <GeneralMarkup key={general.updated_at} rule={general} editable={editable} /> : <p className="text-sm text-ink-muted">Cargando…</p>}
        </Section>
        <Section
          title="Markup por rubro"
          description="Vacío = usa el del rubro padre o el general. Una subcategoría sin markup toma el de su rubro."
        >
          {rules.data ? <CategoryMarkups rules={rules.data} editable={editable} /> : null}
        </Section>
        <Section title="Por producto y por cliente" description="Prioridad: cliente › producto › rubro › general.">
          {rules.data ? <SpecificRules rules={rules.data} editable={editable} /> : null}
        </Section>
        <Section
          title="Cargos sobre la venta"
          description="IIBB, impuesto al cheque, comisiones: se descuentan de la venta para calcular el margen real."
        >
          <SaleCharges editable={editable} />
        </Section>
        <Section title="Redondeo, margen mínimo y costos">
          {settings.data ? <GeneralSettings settings={settings.data} editable={editable} /> : null}
          {settings.isError ? <Notice tone="error">{errorMessage(settings.error)}</Notice> : null}
        </Section>
        <Section
          title="Tipo de cambio"
          description="Para presentar presupuestos en dólares. Cada presupuesto guarda el que usó."
        >
          <ExchangeRates />
        </Section>
      </div>
    </>
  );
}
