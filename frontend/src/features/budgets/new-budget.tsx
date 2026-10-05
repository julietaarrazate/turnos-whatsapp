"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { SelectField, TextField } from "@/components/ui/field";
import { Notice } from "@/components/ui/notice";
import { PageHeader } from "@/components/ui/page-header";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import type { Schemas } from "@/lib/api/types";
import { textValue } from "@/lib/form";

import { budgetKey } from "./keys";

/** Una clave por intento de alta: si la red falla y se reintenta, no se duplica. */
function newIdempotencyKey(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function ClientPicker({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const listId = useId();
  const clients = useQuery({
    queryKey: ["clients", "picker", value.trim()],
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/clients", { params: { query: { q: value.trim() || undefined, limit: 20 } } })),
  });
  return (
    <>
      <TextField
        label="Cliente"
        name="client"
        required
        autoFocus
        autoComplete="off"
        list={listId}
        value={value}
        maxLength={200}
        onChange={(e) => onChange(e.target.value)}
        hint="Elegí uno existente o escribí el nombre de uno nuevo."
      />
      <datalist id={listId}>
        {clients.data?.items.map((client) => (
          <option key={client.id} value={client.name} />
        ))}
      </datalist>
    </>
  );
}

/** B-01: cliente → evento (fecha opcional, días) → editor, en un solo paso. */
export function NewBudget() {
  const router = useRouter();
  const params = useSearchParams();
  const queryClient = useQueryClient();
  const eventId = params.get("event");
  const fromId = params.get("from"); // duplicar un presupuesto existente
  const [client, setClient] = useState("");
  const [idempotencyKey] = useState(newIdempotencyKey);
  const event = useQuery({
    queryKey: ["events", "detail", eventId],
    queryFn: async () => unwrap(await api.GET("/api/v1/events/{event_id}", { params: { path: { event_id: eventId ?? "" } } })),
    enabled: Boolean(eventId),
  });
  const source = useQuery({
    queryKey: ["budgets", "detail", fromId],
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/budgets/{budget_id}", { params: { path: { budget_id: fromId ?? "" } } })),
    enabled: Boolean(fromId),
  });
  const duplicate = useMutation({
    mutationFn: async (body: Schemas["DuplicateIn"]) =>
      unwrap(
        await api.POST("/api/v1/budgets/{budget_id}/duplicate", {
          params: { path: { budget_id: fromId ?? "" }, header: { "Idempotency-Key": idempotencyKey } },
          body,
        }),
      ),
    onSuccess: (data) => {
      queryClient.setQueryData(budgetKey(data.budget.id), data.budget);
      router.replace(`/budgets/${data.budget.id}?costos=${data.costs_changed}&reglas=${data.rules_changed}`);
    },
  });
  const create = useMutation({
    mutationFn: async (body: Schemas["BudgetCreate"]) =>
      unwrap(await api.POST("/api/v1/budgets", { body, headers: { "Idempotency-Key": idempotencyKey } })),
    onSuccess: (data) => {
      queryClient.setQueryData(budgetKey(data.id), data);
      router.replace(`/budgets/${data.id}`);
    },
  });

  return (
    <>
      <PageHeader
        title={fromId ? "Duplicar presupuesto" : "Nuevo presupuesto"}
        description={
          fromId
            ? source.data
              ? `Copia de #${source.data.number} · ${source.data.title}, con los costos y reglas de hoy.`
              : undefined
            : event.data
              ? `Para ${event.data.name} (${event.data.client_name})`
              : "Cliente, evento y al editor."
        }
      />
      <form
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          const form = new FormData(e.currentTarget);
          const currency = String(form.get("currency")) as Schemas["BudgetCreate"]["currency"];
          if (eventId) {
            create.mutate({ event_id: eventId, currency, title: textValue(form, "title") });
            return;
          }
          const start = textValue(form, "start_date");
          const newEvent = {
            client_name: client.trim(),
            name: String(form.get("event_name")).trim(),
            start_date: start,
            end_date: null,
            event_days: Number(form.get("event_days") || 1),
            setup_days: 0,
            teardown_days: 0,
            city: textValue(form, "city"),
          };
          if (fromId) {
            duplicate.mutate({ event: newEvent, title: null });
            return;
          }
          create.mutate({
            currency,
            title: null,
            event: {
              client_name: client.trim(),
              name: String(form.get("event_name")).trim(),
              start_date: start,
              end_date: null,
              event_days: Number(form.get("event_days") || 1),
              setup_days: 0,
              teardown_days: 0,
              city: textValue(form, "city"),
            },
          });
        }}
      >
        <section className="grid gap-4 rounded-xl border border-line bg-surface p-5 sm:grid-cols-2">
          {eventId ? (
            <div className="sm:col-span-2">
              <TextField label="Título (opcional)" name="title" maxLength={200} placeholder={event.data?.name} />
            </div>
          ) : (
            <>
              <div className="sm:col-span-2">
                <ClientPicker value={client} onChange={setClient} />
              </div>
              <div className="sm:col-span-2">
                <TextField label="Evento" name="event_name" required maxLength={200} placeholder="Ej.: Convención anual" />
              </div>
              <TextField label="Fecha (opcional)" name="start_date" type="date" hint="Si todavía no está confirmada, dejala vacía." />
              <TextField
                label="Días de evento"
                name="event_days"
                type="number"
                min={1}
                max={365}
                defaultValue={1}
                hint="Los ítems por día se multiplican por esto."
              />
              <TextField label="Ciudad (opcional)" name="city" maxLength={120} />
            </>
          )}
          {fromId ? null : (
            <SelectField
              label="Moneda de la propuesta"
              name="currency"
              defaultValue="ARS"
              options={[
                { value: "ARS", label: "Pesos" },
                { value: "USD", label: "Dólares (cliente del exterior)" },
              ]}
            />
          )}
        </section>
        {create.isError ? <Notice tone="error">{errorMessage(create.error)}</Notice> : null}
        {duplicate.isError ? <Notice tone="error">{errorMessage(duplicate.error)}</Notice> : null}
        <div>
          <Button type="submit" size="lg" loading={create.isPending || duplicate.isPending}>
            {fromId ? "Duplicar" : "Crear y armar el presupuesto"}
          </Button>
        </div>
      </form>
    </>
  );
}
