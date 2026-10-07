"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { CheckboxField, SelectField, TextField } from "@/components/ui/field";
import { Notice } from "@/components/ui/notice";
import { EVENTS_KEY } from "@/features/budgets/keys";
import { IVA_OPTIONS, useCategories } from "@/features/catalog/shared";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import type { Schemas } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatDay } from "@/lib/format/date";
import { formatMoney, formatPercentCompact } from "@/lib/format/number";
import { parseDecimalAR } from "@/lib/parse/number";

type Expenses = Schemas["ExpensesOut"];
type Row = Schemas["ComparisonRow"];

export const expensesKey = (id: string) => [...EVENTS_KEY, "expenses", id] as const;

const UNBUDGETED = "";

function newKey(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
}

/** "+20 %" / "−5 %" / "en presupuesto". */
function deviation(rate: string | null): string {
  if (rate === null) return "";
  if (Number(rate) === 0) return "en presupuesto";
  return rate.startsWith("-") ? `−${formatPercentCompact(rate.slice(1))}` : `+${formatPercentCompact(rate)}`;
}

function RowLine({ row }: { row: Row }) {
  const over = row.delta !== null && !row.delta.startsWith("-") && row.delta !== "0.00";
  return (
    <li className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 px-4 py-2.5 text-sm">
      <span className="min-w-0 flex-1">
        <span className="font-medium">{row.label}</span>
        {row.section ? <span className="text-ink-muted"> · {row.section}</span> : null}
      </span>
      <span className="tabular-nums text-ink-muted">
        {row.budgeted !== null ? `presupuestado ${formatMoney(row.budgeted)} · ` : ""}real {formatMoney(row.actual)}
      </span>
      {row.delta_rate !== null ? (
        <span className={cn("tabular-nums font-medium", over ? "text-danger" : "text-success")}>{deviation(row.delta_rate)}</span>
      ) : null}
    </li>
  );
}

function ExpenseForm({ id, data, onSaved }: { id: string; data: Expenses; onSaved: (feedback: string) => void }) {
  const queryClient = useQueryClient();
  const categories = useCategories();
  const [key, setKey] = useState(newKey);
  const [amount, setAmount] = useState("");
  const [lineKey, setLineKey] = useState(UNBUDGETED);
  const [currency, setCurrency] = useState<"ARS" | "USD">("ARS");
  const [includesIva, setIncludesIva] = useState(true);
  const create = useMutation({
    mutationFn: async (body: Schemas["ExpenseIn"]) =>
      unwrap(
        await api.POST("/api/v1/events/{event_id}/expenses", {
          params: { path: { event_id: id }, header: { "Idempotency-Key": key } },
          body,
        }),
      ),
    onSuccess: (result, body) => {
      queryClient.setQueryData(expensesKey(id), result);
      const row = result.comparison.find((r) => r.key === body.line_key);
      onSaved(
        row && row.budgeted !== null
          ? `${row.label}: presupuestado ${formatMoney(row.budgeted)} · real ${formatMoney(row.actual)} · ${deviation(row.delta_rate)}`
          : "Gasto cargado (no estaba presupuestado).",
      );
      setKey(newKey());
      setAmount("");
      setLineKey(UNBUDGETED);
    },
  });
  const parsed = parseDecimalAR(amount);
  const line = data.lines.find((l) => l.line_key === lineKey);
  const sections = [...new Set(data.lines.map((l) => l.section))];

  return (
    <form
      aria-label="Nuevo gasto"
      className="grid gap-3 rounded-xl border border-line bg-surface p-4 sm:grid-cols-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (!parsed) return;
        const form = new FormData(e.currentTarget);
        const fx = currency === "USD" ? parseDecimalAR(String(form.get("fx_rate") ?? "")) : null;
        create.mutate({
          description: String(form.get("description")).trim(),
          amount: parsed,
          currency,
          amount_includes_iva: includesIva,
          iva_rate: String(form.get("iva_rate") ?? "0.21"),
          fx_rate: fx,
          expense_date: String(form.get("expense_date") || "") || null,
          line_key: lineKey || null,
          supplier_id: null,
          category_id: lineKey ? null : String(form.get("category_id") || "") || null,
        });
      }}
    >
      <TextField
        label="Monto"
        name="amount"
        inputMode="decimal"
        required
        autoFocus
        value={amount}
        onChange={(e) => setAmount(e.target.value)}
        error={amount && !parsed ? "Revisá el monto (ej.: 150.000,50)" : undefined}
        className="text-lg"
      />
      <TextField label="Descripción" name="description" required maxLength={200} placeholder="Ej.: Factura flete" />
      <label className="flex flex-col gap-1 text-sm sm:col-span-2">
        <span className="text-ink-muted">Línea del presupuesto</span>
        <select
          aria-label="Línea del presupuesto"
          className="h-11 rounded-lg border border-line bg-surface px-3 sm:h-10"
          value={lineKey}
          onChange={(e) => setLineKey(e.target.value)}
        >
          <option value={UNBUDGETED}>No estaba presupuestado</option>
          {sections.map((section) => (
            <optgroup key={section} label={section || "Presupuesto"}>
              {data.lines
                .filter((l) => l.section === section)
                .map((l) => (
                  <option key={l.line_key} value={l.line_key}>
                    {l.name}
                    {l.supplier_name ? ` · ${l.supplier_name}` : ""}
                  </option>
                ))}
            </optgroup>
          ))}
        </select>
        {line ? (
          <span className="text-xs text-ink-muted">
            Presupuestado {formatMoney(line.budgeted)}
            {line.supplier_name ? ` · proveedor ${line.supplier_name}` : ""}
          </span>
        ) : null}
      </label>
      {lineKey ? null : (
        <SelectField
          label="Categoría"
          name="category_id"
          required
          options={[{ value: "", label: "Elegí una categoría" }, ...(categories.data ?? []).map((c) => ({ value: c.id, label: c.name }))]}
        />
      )}
      <SelectField
        label="Moneda"
        value={currency}
        onChange={(e) => setCurrency(e.target.value as "ARS" | "USD")}
        options={[
          { value: "ARS", label: "Pesos" },
          { value: "USD", label: "Dólares" },
        ]}
      />
      {currency === "USD" ? (
        <TextField label="Tipo de cambio (opcional)" name="fx_rate" inputMode="decimal" hint="Vacío: el último cargado." />
      ) : null}
      <TextField label="Fecha" name="expense_date" type="date" hint="Vacía: hoy." />
      <SelectField label="IVA del comprobante" name="iva_rate" defaultValue="0.21" options={IVA_OPTIONS} />
      <CheckboxField label="El monto incluye IVA" checked={includesIva} onChange={(e) => setIncludesIva(e.target.checked)} />
      <div className="sm:col-span-2">
        <Button type="submit" size="lg" loading={create.isPending} disabled={!parsed}>
          Guardar gasto
        </Button>
      </div>
      {create.isError ? (
        <div className="sm:col-span-2">
          <Notice tone="error">{errorMessage(create.error)}</Notice>
        </div>
      ) : null}
    </form>
  );
}

function ExpenseItem({ expense, id, editable }: { expense: Schemas["ExpenseOut"]; id: string; editable: boolean }) {
  const queryClient = useQueryClient();
  const remove = useMutation({
    mutationFn: async () =>
      unwrap(await api.DELETE("/api/v1/expenses/{expense_id}", { params: { path: { expense_id: expense.id } } })),
    onSuccess: (result) => queryClient.setQueryData(expensesKey(id), result),
  });
  return (
    <li className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 px-4 py-2.5 text-sm">
      <span className="text-ink-muted">{formatDay(expense.expense_date)}</span>
      <span className="min-w-0 flex-1">
        {expense.description}
        <span className="text-ink-muted">
          {" · "}
          {expense.line_name ?? (expense.category_name ? `${expense.category_name} (no presupuestado)` : "no presupuestado")}
          {expense.supplier_name ? ` · ${expense.supplier_name}` : ""}
        </span>
      </span>
      <span className="tabular-nums">
        {formatMoney(expense.amount, expense.currency)}
        {expense.amount_base !== expense.amount || expense.currency !== "ARS" ? (
          <span className="text-ink-muted"> → {formatMoney(expense.amount_base)}</span>
        ) : null}
      </span>
      {editable ? (
        <Button
          size="sm"
          variant="ghost"
          aria-label={`Borrar gasto ${expense.description}`}
          loading={remove.isPending}
          onClick={() => window.confirm(`¿Borrar el gasto "${expense.description}"?`) && remove.mutate()}
        >
          <Trash2 className="size-4" aria-hidden />
        </Button>
      ) : null}
      {remove.isError ? <Notice tone="error">{errorMessage(remove.error)}</Notice> : null}
    </li>
  );
}

/** Pestaña Gastos: costos reales del evento y presupuestado vs real (O-04, journey J6). */
export function EventExpenses({ id }: { id: string }) {
  const [adding, setAdding] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const expenses = useQuery({
    queryKey: expensesKey(id),
    queryFn: async () => unwrap(await api.GET("/api/v1/events/{event_id}/expenses", { params: { path: { event_id: id } } })),
  });
  if (expenses.isPending) return <p className="text-sm text-ink-muted">Cargando…</p>;
  if (expenses.isError) return <Notice tone="error">{errorMessage(expenses.error)}</Notice>;
  const data = expenses.data;

  return (
    <div className="flex flex-col gap-4">
      <section aria-label="Presupuestado vs real" className="rounded-xl border border-line bg-surface">
        <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-line px-4 py-3">
          <h2 className="font-semibold">Presupuestado vs real</h2>
          <span className="text-sm tabular-nums text-ink-muted">
            {data.has_baseline ? `presupuestado ${formatMoney(data.budgeted_total)} · ` : ""}real {formatMoney(data.actual_total)}
            {data.delta_rate !== null ? ` · ${deviation(data.delta_rate)}` : ""}
          </span>
        </div>
        {data.comparison.length ? (
          <ul className="divide-y divide-line">
            {data.comparison.map((row) => (
              <RowLine key={row.key} row={row} />
            ))}
          </ul>
        ) : (
          <p className="px-4 py-3 text-sm text-ink-muted">
            {data.has_baseline ? "Todavía no hay gastos." : "El evento todavía no tiene un presupuesto aprobado."}
          </p>
        )}
      </section>

      {feedback ? <Notice tone="success">{feedback}</Notice> : null}
      {data.editable ? (
        adding ? (
          <ExpenseForm id={id} data={data} onSaved={setFeedback} />
        ) : (
          <div>
            <Button size="lg" onClick={() => setAdding(true)}>
              <Plus className="size-4" aria-hidden /> Gasto
            </Button>
          </div>
        )
      ) : null}

      <section aria-label="Gastos" className="rounded-xl border border-line bg-surface">
        <h2 className="border-b border-line px-4 py-3 font-semibold">Gastos</h2>
        {data.items.length ? (
          <ul className="divide-y divide-line">
            {data.items.map((expense) => (
              <ExpenseItem key={expense.id} expense={expense} id={id} editable={data.editable} />
            ))}
          </ul>
        ) : (
          <p className="px-4 py-3 text-sm text-ink-muted">Sin gastos cargados.</p>
        )}
      </section>
    </div>
  );
}
