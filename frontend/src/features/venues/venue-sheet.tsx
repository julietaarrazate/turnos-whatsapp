"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MapPin, Pencil } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Notice } from "@/components/ui/notice";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import type { Schemas } from "@/lib/api/types";
import { formatDate } from "@/lib/format/date";

type Sheet = Schemas["VenueSheetOut"];
type SheetIn = Schemas["VenueSheetIn"];

const venueKey = (eventId: string) => ["venue-sheet", eventId] as const;

/** Lo que se pregunta siempre antes de montar en un lugar. */
export const FIELDS: { key: keyof SheetIn; label: string; placeholder: string; long?: boolean }[] = [
  { key: "address", label: "Dirección", placeholder: "Av. Costanera Rafael Obligado 1221, CABA" },
  { key: "maps_url", label: "Link de Google Maps", placeholder: "https://maps.app.goo.gl/…" },
  { key: "load_in", label: "Carga y accesos", placeholder: "Por calle Sarmiento, de 7 a 10. Estacionamiento para camiones en playón 3.", long: true },
  { key: "measures", label: "Medidas", placeholder: "Puerta de carga 3,20 m de alto. Montacargas 1.500 kg. Altura del salón 6 m.", long: true },
  { key: "rules", label: "Reglas del predio", placeholder: "Seguro con cláusula de no repetición, ART del personal, prohibido perforar el piso.", long: true },
  { key: "contacts", label: "Contactos", placeholder: "Seguridad: Juan 11 5555-0000. Técnica: Marta 11 5555-1111.", long: true },
  { key: "notes", label: "Notas", placeholder: "Lo que aprendimos la última vez.", long: true },
];

/** Texto con los saltos de línea como se escribieron. */
function Text({ value }: { value: string }) {
  return <p className="text-sm whitespace-pre-line">{value}</p>;
}

function SheetForm({ eventId, sheet, onDone }: { eventId: string; sheet: Sheet | null; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [values, setValues] = useState<SheetIn>(() =>
    Object.fromEntries(FIELDS.map((f) => [f.key, sheet?.[f.key] ?? ""])) as SheetIn,
  );
  const save = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.PUT("/api/v1/events/{event_id}/venue-sheet", {
          params: { path: { event_id: eventId } },
          body: values,
        }),
      ),
    onSuccess: (data) => {
      queryClient.setQueryData(venueKey(eventId), data);
      onDone();
    },
  });
  return (
    <form
      aria-label="Ficha del lugar"
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      {FIELDS.map((field) => (
        <label key={field.key} className="flex flex-col gap-1.5 text-sm font-medium">
          {field.label}
          {field.long ? (
            <textarea
              value={values[field.key] ?? ""}
              onChange={(e) => setValues({ ...values, [field.key]: e.currentTarget.value })}
              rows={2}
              maxLength={2000}
              placeholder={field.placeholder}
              className="rounded-lg border border-line bg-surface px-3 py-2 text-base font-normal sm:text-sm"
            />
          ) : (
            <input
              value={values[field.key] ?? ""}
              onChange={(e) => setValues({ ...values, [field.key]: e.currentTarget.value })}
              type={field.key === "maps_url" ? "url" : "text"}
              maxLength={field.key === "maps_url" ? 1000 : 300}
              placeholder={field.placeholder}
              className="h-10 rounded-lg border border-line bg-surface px-3 text-base font-normal sm:text-sm"
            />
          )}
        </label>
      ))}
      <div className="flex gap-2">
        <Button type="submit" loading={save.isPending}>
          Guardar ficha
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancelar
        </Button>
      </div>
      {save.isError ? <Notice tone="error">{errorMessage(save.error)}</Notice> : null}
    </form>
  );
}

/** La ficha del lugar en el resumen del evento: se carga una vez y sirve para el próximo evento. */
export function VenueSheet({ eventId }: { eventId: string }) {
  const venue = useQuery({
    queryKey: venueKey(eventId),
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/events/{event_id}/venue-sheet", { params: { path: { event_id: eventId } } })),
  });
  const [editing, setEditing] = useState(false);
  if (!venue.data) return venue.isError ? <Notice tone="error">{errorMessage(venue.error)}</Notice> : null;
  const { venue: name, sheet, other_events: others, can_edit: canEdit } = venue.data;
  const filled = sheet ? FIELDS.filter((f) => sheet[f.key]) : [];

  return (
    <section aria-labelledby="venue-title" className="my-4 rounded-xl border border-line bg-surface p-5">
      <div className="mb-3 flex items-start justify-between gap-2">
        <div>
          <h2 id="venue-title" className="flex items-center gap-2 font-semibold">
            <MapPin className="size-4 text-brand" aria-hidden /> {name ? `Ficha del lugar: ${name}` : "Ficha del lugar"}
          </h2>
          {name && others > 0 ? (
            <p className="text-xs text-ink-muted">
              Ya trabajaron ahí en {others} {others === 1 ? "evento" : "eventos"}: la ficha es la misma para todos.
            </p>
          ) : null}
        </div>
        {name && canEdit && !editing ? (
          <Button size="sm" variant="secondary" onClick={() => setEditing(true)}>
            <Pencil className="size-4" aria-hidden /> {sheet ? "Editar" : "Armar ficha"}
          </Button>
        ) : null}
      </div>
      {!name ? (
        <p className="text-sm text-ink-muted">Cargá el lugar del evento para ver o armar su ficha (accesos, carga, medidas, contactos).</p>
      ) : editing ? (
        <SheetForm eventId={eventId} sheet={sheet} onDone={() => setEditing(false)} />
      ) : filled.length === 0 ? (
        <p className="text-sm text-ink-muted">
          Todavía no hay ficha de este lugar. Anotá cómo es la carga, las medidas y los contactos: el próximo evento acá ya los tiene.
        </p>
      ) : (
        <dl className="grid gap-3 sm:grid-cols-2">
          {filled.map((field) => (
            <div key={field.key} className={field.long ? "sm:col-span-2" : undefined}>
              <dt className="text-xs font-semibold text-ink-muted">{field.label}</dt>
              <dd>
                {field.key === "maps_url" ? (
                  <a href={sheet![field.key]!} target="_blank" rel="noopener noreferrer" className="text-sm text-accent underline">
                    Abrir en el mapa
                  </a>
                ) : (
                  <Text value={sheet![field.key]!} />
                )}
              </dd>
            </div>
          ))}
          <p className="text-xs text-ink-muted sm:col-span-2">
            Actualizada por {sheet!.updated_by_name} el {formatDate(sheet!.updated_at)}
          </p>
        </dl>
      )}
    </section>
  );
}
