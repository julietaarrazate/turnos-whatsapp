"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { SelectField, TextField } from "@/components/ui/field";
import { Notice } from "@/components/ui/notice";
import { PageHeader } from "@/components/ui/page-header";
import { Switch } from "@/components/ui/switch";
import { ME_QUERY_KEY, useSession } from "@/features/auth/session";
import { StorageMeter } from "@/features/settings/storage-meter";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import type { Organization } from "@/lib/api/types";

const ORG_KEY = ["organization"] as const;

const TAX_OPTIONS = [
  { value: "RI", label: "Responsable Inscripto" },
  { value: "MONOTRIBUTO", label: "Monotributo" },
  { value: "EXENTO", label: "Exento" },
];

function Section({ title, description, children }: { title: string; description?: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-line bg-surface p-5">
      <h2 className="font-semibold">{title}</h2>
      {description ? <p className="mt-1 text-sm text-ink-muted">{description}</p> : null}
      <div className="mt-4">{children}</div>
    </section>
  );
}

export function OrganizationSettings() {
  const { can } = useSession();
  const queryClient = useQueryClient();
  const org = useQuery({
    queryKey: ORG_KEY,
    queryFn: async () => unwrap(await api.GET("/api/v1/organization")),
  });

  const update = useMutation({
    mutationFn: async (body: { name?: string; viewer_sees_financials?: boolean; follow_up_days?: number }) =>
      unwrap(await api.PATCH("/api/v1/organization", { body })),
    onSuccess: (data) => {
      queryClient.setQueryData(ORG_KEY, data);
      void queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY });
    },
  });

  const fiscal = useMutation({
    mutationFn: async (body: { legal_name: string | null; tax_id: string | null; tax_condition: Organization["tax_condition"] }) =>
      unwrap(await api.PATCH("/api/v1/organization/fiscal", { body })),
    onSuccess: (data) => queryClient.setQueryData(ORG_KEY, data),
  });

  if (org.isPending) return <p className="text-sm text-ink-muted">Cargando…</p>;
  if (org.isError) return <Notice tone="error">{errorMessage(org.error)}</Notice>;
  const data = org.data;
  const canEdit = can("org.settings.manage");
  const canFiscal = can("org.fiscal.manage");

  return (
    <>
      <PageHeader title="Organización" description="Datos de tu productora." />
      <div className="flex flex-col gap-4">
        <StorageMeter />
        <Section title="General">
          <form
            className="flex flex-col gap-4 sm:flex-row sm:items-end"
            onSubmit={(event) => {
              event.preventDefault();
              update.mutate({ name: String(new FormData(event.currentTarget).get("name")) });
            }}
          >
            <div className="flex-1">
              <TextField label="Nombre" name="name" defaultValue={data.name} disabled={!canEdit} required />
            </div>
            {canEdit ? (
              <Button type="submit" variant="secondary" loading={update.isPending}>
                Guardar
              </Button>
            ) : null}
          </form>
        </Section>

        <Section title="Visibilidad" description="Quién ve los números internos.">
          <Switch
            label="Solo lectura ve costos y márgenes"
            description="Producción siempre ve costos y nunca márgenes."
            checked={data.viewer_sees_financials}
            disabled={!canEdit || update.isPending}
            onChange={(value) => update.mutate({ viewer_sees_financials: value })}
          />
          <label className="flex flex-wrap items-center gap-2 text-sm">
            <span>&ldquo;Para seguir&rdquo;: propuestas sin respuesta después de</span>
            <input
              key={data.follow_up_days}
              type="number"
              min={1}
              max={60}
              defaultValue={data.follow_up_days}
              disabled={!canEdit || update.isPending}
              aria-label="Días para seguir"
              className="h-9 w-16 rounded-lg border border-line bg-surface px-2 text-right tabular-nums"
              onBlur={(e) => {
                const days = Number(e.currentTarget.value);
                if (Number.isInteger(days) && days >= 1 && days <= 60 && days !== data.follow_up_days) {
                  update.mutate({ follow_up_days: days });
                }
              }}
            />
            <span>días</span>
          </label>
        </Section>
        {update.isError ? <Notice tone="error">{errorMessage(update.error)}</Notice> : null}

        <Section title="Datos fiscales" description="Definen cómo se calculan el IVA y el costo efectivo.">
          <form
            className="grid gap-4 sm:grid-cols-2"
            onSubmit={(event) => {
              event.preventDefault();
              const form = new FormData(event.currentTarget);
              fiscal.mutate({
                legal_name: String(form.get("legal_name")) || null,
                tax_id: String(form.get("tax_id")) || null,
                tax_condition: String(form.get("tax_condition")) as Organization["tax_condition"],
              });
            }}
          >
            <TextField label="Razón social" name="legal_name" defaultValue={data.legal_name ?? ""} disabled={!canFiscal} />
            <TextField
              label="CUIT"
              name="tax_id"
              defaultValue={data.tax_id ?? ""}
              placeholder="30-12345678-9"
              inputMode="numeric"
              disabled={!canFiscal}
            />
            <SelectField
              label="Condición frente al IVA"
              name="tax_condition"
              defaultValue={data.tax_condition}
              options={TAX_OPTIONS}
              disabled={!canFiscal}
            />
            {canFiscal ? (
              <div className="flex items-end">
                <Button type="submit" variant="secondary" loading={fiscal.isPending}>
                  Guardar datos fiscales
                </Button>
              </div>
            ) : (
              <p className="self-end text-sm text-ink-muted">Solo el/la dueño/a puede cambiar estos datos.</p>
            )}
          </form>
          {fiscal.isError ? (
            <div className="mt-3">
              <Notice tone="error">{errorMessage(fiscal.error)}</Notice>
            </div>
          ) : null}
          {fiscal.isSuccess ? (
            <div className="mt-3">
              <Notice tone="success">Datos fiscales guardados.</Notice>
            </div>
          ) : null}
        </Section>
      </div>
    </>
  );
}
