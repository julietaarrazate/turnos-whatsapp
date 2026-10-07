"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Trash2, X } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Notice } from "@/components/ui/notice";
import { useSession } from "@/features/auth/session";
import { EVENTS_KEY } from "@/features/budgets/keys";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import type { Schemas } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatDay } from "@/lib/format/date";
import { formatMoney, formatQuantity } from "@/lib/format/number";

type Supplier = Schemas["EventSupplierOut"];
type Task = Schemas["TaskOut"];

export const productionKey = (id: string) => [...EVENTS_KEY, "production", id] as const;

const HIRE: Record<Supplier["status"], { label: string; tone: string }> = {
  TO_HIRE: { label: "Cotizado", tone: "bg-warning/15 text-warning" },
  CONFIRMED: { label: "Confirmado", tone: "bg-accent/10 text-accent" },
  INVOICED: { label: "Factura cargada", tone: "bg-warning/15 text-warning" },
  PAID: { label: "Pagado", tone: "bg-success/10 text-success" },
  CANCELLED: { label: "Cancelado", tone: "bg-subtle text-ink-muted" },
};

function SupplierRow({ row, eventId, editable }: { row: Supplier; eventId: string; editable: boolean }) {
  const queryClient = useQueryClient();
  const update = useMutation({
    mutationFn: async (body: Schemas["EventSupplierUpdate"]) =>
      unwrap(
        await api.PATCH("/api/v1/event-suppliers/{event_supplier_id}", {
          params: { path: { event_supplier_id: row.id } },
          body,
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: productionKey(eventId) }),
  });
  const name = row.supplier_name ?? "Sin proveedor (propio o a definir)";
  return (
    <li className="flex flex-col gap-2 px-4 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{name}</span>
        <span className={cn("rounded px-1.5 py-0.5 text-xs", HIRE[row.status].tone)}>{HIRE[row.status].label}</span>
        {row.budgeted_cost !== null ? (
          <span className="ml-auto text-sm tabular-nums text-ink-muted">Presupuestado {formatMoney(row.budgeted_cost)}</span>
        ) : null}
      </div>
      <ul className="text-sm text-ink-muted">
        {row.items.map((item) => (
          <li key={item.line_key}>
            {item.name} · {formatQuantity(item.quantity)} {item.unit_code}
            {item.days > 1 ? ` × ${item.days} días` : ""}
          </li>
        ))}
      </ul>
      {row.notes ? <p className="text-sm">{row.notes}</p> : null}
      {row.invoice_number || row.payment_terms ? (
        <p className="text-sm text-ink-muted">
          {row.invoice_number ? `Factura ${row.invoice_number}` : ""}
          {row.invoice_number && row.payment_terms ? " · " : ""}
          {row.payment_terms ?? ""}
        </p>
      ) : null}
      {editable && row.status !== "CANCELLED" && row.status !== "PAID" ? (
        <div className="flex flex-wrap gap-2">
          {row.status === "TO_HIRE" ? (
            <Button size="sm" loading={update.isPending} onClick={() => update.mutate({ status: "CONFIRMED" })}>
              <Check className="size-4" aria-hidden /> Confirmar {row.supplier_name ?? ""}
            </Button>
          ) : null}
          {row.status === "TO_HIRE" || row.status === "CONFIRMED" ? (
            <Button
              size="sm"
              variant="secondary"
              onClick={() => {
                const invoice = window.prompt("Nº de factura del proveedor", row.invoice_number ?? "");
                if (invoice === null) return;
                const terms = window.prompt("Condición de pago (opcional)", row.payment_terms ?? "");
                update.mutate({ status: "INVOICED", invoice_number: invoice, payment_terms: terms ?? row.payment_terms });
              }}
            >
              Cargar factura
            </Button>
          ) : null}
          {row.status === "INVOICED" ? (
            <Button size="sm" loading={update.isPending} onClick={() => update.mutate({ status: "PAID" })}>
              <Check className="size-4" aria-hidden /> Marcar pagado
            </Button>
          ) : null}
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              const notes = window.prompt("Nota para este proveedor", row.notes ?? "");
              if (notes !== null) update.mutate({ notes });
            }}
          >
            Nota
          </Button>
          {row.status === "TO_HIRE" || row.status === "CONFIRMED" ? (
            <Button
              size="sm"
              variant="ghost"
              className="text-danger"
              onClick={() => window.confirm(`¿Cancelar la contratación de ${name}?`) && update.mutate({ status: "CANCELLED" })}
            >
              <X className="size-4" aria-hidden /> Cancelar
            </Button>
          ) : null}
        </div>
      ) : null}
      {update.isError ? <Notice tone="error">{errorMessage(update.error)}</Notice> : null}
    </li>
  );
}

function TaskRow({ task, eventId, editable, members }: { task: Task; eventId: string; editable: boolean; members: Schemas["MemberOut"][] }) {
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: productionKey(eventId) });
  // Optimista: el tilde se ve al instante; si falla, vuelve a lo que diga el servidor.
  const [pendingDone, setPendingDone] = useState<boolean | null>(null);
  const update = useMutation({
    mutationFn: async (body: Schemas["TaskUpdate"]) =>
      unwrap(await api.PATCH("/api/v1/tasks/{task_id}", { params: { path: { task_id: task.id } }, body })),
    onSettled: async () => {
      await refresh();
      setPendingDone(null);
    },
  });
  const remove = useMutation({
    mutationFn: async () => unwrap(await api.DELETE("/api/v1/tasks/{task_id}", { params: { path: { task_id: task.id } } })),
    onSuccess: refresh,
  });
  const done = pendingDone ?? task.status === "DONE";
  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5 text-sm">
      <input
        type="checkbox"
        className="size-5 accent-accent"
        checked={done}
        disabled={!editable}
        aria-label={`Hecha: ${task.title}`}
        onChange={(e) => {
          const checked = e.currentTarget.checked;
          setPendingDone(checked);
          update.mutate({ status: checked ? "DONE" : "TODO" });
        }}
      />
      <span className={cn("min-w-0 flex-1", done && "text-ink-muted line-through")}>{task.title}</span>
      {editable ? (
        <select
          aria-label={`Responsable de ${task.title}`}
          className="h-8 rounded-lg border border-line bg-surface px-2 text-sm"
          value={task.assignee_user_id ?? ""}
          onChange={(e) => update.mutate({ assignee_user_id: e.currentTarget.value || null })}
        >
          <option value="">Sin responsable</option>
          {members.map((m) => (
            <option key={m.user_id} value={m.user_id}>
              {m.name}
            </option>
          ))}
        </select>
      ) : task.assignee_name ? (
        <span className="text-ink-muted">{task.assignee_name}</span>
      ) : null}
      {task.due_date ? <span className="text-ink-muted">{formatDay(task.due_date)}</span> : null}
      {editable ? (
        <Button size="sm" variant="ghost" aria-label={`Borrar ${task.title}`} onClick={() => remove.mutate()}>
          <Trash2 className="size-4" aria-hidden />
        </Button>
      ) : null}
      {update.isError ? <Notice tone="error">{errorMessage(update.error)}</Notice> : null}
    </li>
  );
}

/** Pestaña Producción: lista de contratación por proveedor y tareas (O-02, O-03). */
export function EventProduction({ id }: { id: string }) {
  const { can } = useSession();
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("");
  const production = useQuery({
    queryKey: productionKey(id),
    queryFn: async () => unwrap(await api.GET("/api/v1/events/{event_id}/production", { params: { path: { event_id: id } } })),
  });
  const members = useQuery({
    queryKey: ["members", "active"],
    queryFn: async () => unwrap(await api.GET("/api/v1/members")),
    enabled: can("production.manage"),
  });
  const addTask = useMutation({
    mutationFn: async (body: Schemas["TaskIn"]) =>
      unwrap(await api.POST("/api/v1/events/{event_id}/tasks", { params: { path: { event_id: id } }, body })),
    onSuccess: () => {
      setTitle("");
      void queryClient.invalidateQueries({ queryKey: productionKey(id) });
    },
  });
  const editable = can("production.manage");
  const active = (members.data ?? []).filter((m) => m.status === "ACTIVE");

  if (production.isPending) return <p className="text-sm text-ink-muted">Cargando…</p>;
  if (production.isError) return <Notice tone="error">{errorMessage(production.error)}</Notice>;
  const data = production.data;
  if (!data.started) {
    return (
      <Notice tone="info">
        Todavía no se inició la producción. Cuando el evento esté aprobado, tocá <strong>Iniciar producción</strong> en el Resumen: se arma
        la lista de contratación desde el presupuesto aprobado.
      </Notice>
    );
  }
  const toHire = data.suppliers.filter((s) => s.status === "TO_HIRE").length;
  const unpaid = data.suppliers.filter((s) => s.status === "INVOICED").length;
  return (
    <div className="flex flex-col gap-4">
      <section aria-label="Lista de contratación" className="rounded-xl border border-line bg-surface">
        <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-line px-4 py-3">
          <h2 className="font-semibold">Lista de contratación</h2>
          <span className="text-sm text-ink-muted">
            {toHire ? `${toHire} por confirmar` : "Todo confirmado"}
            {unpaid ? ` · ${unpaid} por pagar` : ""}
            {data.budgeted_cost !== null ? ` · presupuestado ${formatMoney(data.budgeted_cost)}` : ""}
          </span>
        </div>
        <ul className="divide-y divide-line">
          {data.suppliers.map((row) => (
            <SupplierRow key={row.id} row={row} eventId={id} editable={editable} />
          ))}
        </ul>
      </section>

      <section aria-label="Tareas" className="rounded-xl border border-line bg-surface">
        <h2 className="border-b border-line px-4 py-3 font-semibold">Tareas</h2>
        <ul className="divide-y divide-line">
          {data.tasks.map((task) => (
            <TaskRow key={task.id} task={task} eventId={id} editable={editable} members={active} />
          ))}
        </ul>
        {editable ? (
          <form
            className="flex gap-2 border-t border-line px-4 py-3"
            onSubmit={(e) => {
              e.preventDefault();
              if (title.trim()) addTask.mutate({ title: title.trim() });
            }}
          >
            <input
              value={title}
              onChange={(e) => setTitle(e.currentTarget.value)}
              maxLength={200}
              aria-label="Nueva tarea"
              placeholder="Agregar una tarea…"
              className="h-10 min-w-0 flex-1 rounded-lg border border-line bg-surface px-3 text-sm"
            />
            <Button type="submit" loading={addTask.isPending}>
              Agregar
            </Button>
          </form>
        ) : null}
        {addTask.isError ? <Notice tone="error">{errorMessage(addTask.error)}</Notice> : null}
      </section>
    </div>
  );
}
