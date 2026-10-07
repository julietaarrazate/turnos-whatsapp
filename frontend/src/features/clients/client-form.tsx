"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ContactsEditor, contactsPayload, newContactKey, type ContactDraft } from "@/components/business/contacts-editor";
import { TAX_CONDITION_OPTIONS } from "@/components/business/tax";
import { Button } from "@/components/ui/button";
import { SelectField, TextAreaField, TextField } from "@/components/ui/field";
import { Notice } from "@/components/ui/notice";
import { PageHeader } from "@/components/ui/page-header";
import { useSession } from "@/features/auth/session";
import { ScopedMarkup } from "@/features/pricing/scoped-markup";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import type { Client, TaxCondition } from "@/lib/api/types";
import { textValue } from "@/lib/form";

import { ClientHistory } from "./client-history";
import { CLIENTS_KEY } from "./clients-list";

function BackLink() {
  return (
    <Link href="/clients" className="mb-3 inline-flex items-center gap-1 text-sm text-ink-muted hover:text-ink">
      <ArrowLeft className="size-4" aria-hidden /> Clientes
    </Link>
  );
}

function ClientEditor({ client }: { client: Client | null }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { can } = useSession();
  const editable = can("clients.edit");
  const [saved, setSaved] = useState(false);
  const [contacts, setContacts] = useState<ContactDraft[]>(
    () => client?.contacts.map((c) => ({ ...c, key: newContactKey() })) ?? [],
  );

  const save = useMutation({
    mutationFn: async (body: Omit<Client, "id" | "contacts"> & { contacts: ReturnType<typeof contactsPayload> }) =>
      client
        ? unwrap(await api.PATCH("/api/v1/clients/{client_id}", { params: { path: { client_id: client.id } }, body }))
        : unwrap(await api.POST("/api/v1/clients", { body })),
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: CLIENTS_KEY });
      queryClient.setQueryData([...CLIENTS_KEY, "detail", data.id], data);
      if (client) setSaved(true);
      else router.replace(`/clients/${data.id}`);
    },
  });
  const remove = useMutation({
    mutationFn: async (id: string) =>
      unwrap(await api.DELETE("/api/v1/clients/{client_id}", { params: { path: { client_id: id } } })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLIENTS_KEY });
      router.replace("/clients");
    },
  });

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        setSaved(false);
        save.mutate({
          name: String(form.get("name")).trim(),
          legal_name: textValue(form, "legal_name"),
          tax_id: textValue(form, "tax_id"),
          tax_condition: textValue(form, "tax_condition") as TaxCondition | null,
          address: textValue(form, "address"),
          city: textValue(form, "city"),
          notes: textValue(form, "notes"),
          contacts: contactsPayload(contacts, true),
        });
      }}
    >
      <fieldset disabled={!editable} className="flex flex-col gap-4">
        <section className="grid gap-4 rounded-xl border border-line bg-surface p-5 sm:grid-cols-2">
          <TextField label="Nombre" name="name" required maxLength={200} defaultValue={client?.name} autoFocus={!client} />
          <TextField label="Razón social" name="legal_name" maxLength={200} defaultValue={client?.legal_name ?? ""} />
          <TextField
            label="CUIT"
            name="tax_id"
            inputMode="numeric"
            pattern="\d{2}-?\d{8}-?\d"
            hint="11 dígitos, con o sin guiones"
            defaultValue={client?.tax_id ?? ""}
          />
          <SelectField
            label="Condición frente al IVA"
            name="tax_condition"
            options={TAX_CONDITION_OPTIONS}
            defaultValue={client?.tax_condition ?? ""}
          />
          <TextField label="Dirección" name="address" maxLength={300} defaultValue={client?.address ?? ""} />
          <TextField label="Ciudad" name="city" maxLength={120} defaultValue={client?.city ?? ""} />
          <div className="sm:col-span-2">
            <TextAreaField label="Notas" name="notes" maxLength={5000} defaultValue={client?.notes ?? ""} />
          </div>
        </section>
        <section className="rounded-xl border border-line bg-surface p-5">
          <ContactsEditor contacts={contacts} onChange={setContacts} withPosition />
        </section>
      </fieldset>
      {save.isError ? <Notice tone="error">{errorMessage(save.error)}</Notice> : null}
      {remove.isError ? <Notice tone="error">{errorMessage(remove.error)}</Notice> : null}
      {saved ? <Notice tone="success">Cambios guardados.</Notice> : null}
      {editable ? (
        <div className="flex flex-wrap justify-between gap-3">
          <Button type="submit" loading={save.isPending}>
            {client ? "Guardar cambios" : "Crear cliente"}
          </Button>
          {client ? (
            <Button
              type="button"
              variant="ghost"
              className="text-danger"
              loading={remove.isPending}
              onClick={() => {
                if (window.confirm(`¿Borrar a ${client.name}? Sus presupuestos anteriores no se modifican.`)) {
                  remove.mutate(client.id);
                }
              }}
            >
              Borrar cliente
            </Button>
          ) : null}
        </div>
      ) : null}
    </form>
  );
}

export function NewClient() {
  return (
    <>
      <BackLink />
      <PageHeader title="Nuevo cliente" />
      <ClientEditor client={null} />
    </>
  );
}

export function ClientDetail({ id }: { id: string }) {
  const client = useQuery({
    queryKey: [...CLIENTS_KEY, "detail", id],
    queryFn: async () => unwrap(await api.GET("/api/v1/clients/{client_id}", { params: { path: { client_id: id } } })),
  });
  return (
    <>
      <BackLink />
      {client.isPending ? <p className="text-sm text-ink-muted">Cargando…</p> : null}
      {client.isError ? <Notice tone="error">{errorMessage(client.error)}</Notice> : null}
      {client.data ? (
        <>
          <PageHeader title={client.data.name} description={client.data.legal_name ?? undefined} />
          <ClientHistory id={client.data.id} />
          <ScopedMarkup scope="CLIENT" scopeId={client.data.id} />
          <ClientEditor key={client.data.id} client={client.data} />
        </>
      ) : null}
    </>
  );
}
