"use client";

import { Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { TextField } from "@/components/ui/field";

export interface ContactDraft {
  key: string;
  name: string;
  position?: string | null;
  email?: string | null;
  phone?: string | null;
  is_primary: boolean;
}

let seq = 0;
export function newContactKey(): string {
  seq += 1;
  return `c${seq}`;
}

/** Contactos editables en memoria; el formulario padre los manda completos (reemplazan). */
export function ContactsEditor({
  contacts,
  onChange,
  withPosition = false,
}: {
  contacts: ContactDraft[];
  onChange: (contacts: ContactDraft[]) => void;
  withPosition?: boolean;
}) {
  function patch(key: string, changes: Partial<ContactDraft>) {
    onChange(
      contacts.map((c) => {
        if (changes.is_primary && c.key !== key) return { ...c, is_primary: false };
        return c.key === key ? { ...c, ...changes } : c;
      }),
    );
  }

  return (
    <fieldset className="flex flex-col gap-3">
      <legend className="mb-2 text-sm font-medium text-ink">Contactos</legend>
      {contacts.length === 0 ? <p className="text-sm text-ink-muted">Sin contactos cargados.</p> : null}
      {contacts.map((contact, index) => (
        <div key={contact.key} className="grid gap-3 rounded-lg border border-line p-3 sm:grid-cols-2">
          <TextField
            label="Nombre"
            value={contact.name}
            required
            maxLength={200}
            onChange={(e) => patch(contact.key, { name: e.target.value })}
          />
          {withPosition ? (
            <TextField
              label="Cargo"
              value={contact.position ?? ""}
              maxLength={120}
              onChange={(e) => patch(contact.key, { position: e.target.value })}
            />
          ) : null}
          <TextField
            label="Email"
            type="email"
            inputMode="email"
            value={contact.email ?? ""}
            onChange={(e) => patch(contact.key, { email: e.target.value })}
          />
          <TextField
            label="Teléfono"
            type="tel"
            inputMode="tel"
            value={contact.phone ?? ""}
            maxLength={50}
            onChange={(e) => patch(contact.key, { phone: e.target.value })}
          />
          <div className="flex items-center justify-between gap-3 sm:col-span-2">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                name="primary-contact"
                className="size-4 accent-accent"
                checked={contact.is_primary}
                onChange={() => patch(contact.key, { is_primary: true })}
              />
              Contacto principal
            </label>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              aria-label={`Quitar contacto ${index + 1}`}
              onClick={() => onChange(contacts.filter((c) => c.key !== contact.key))}
            >
              <Trash2 className="size-4" aria-hidden /> Quitar
            </Button>
          </div>
        </div>
      ))}
      <div>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={() =>
            onChange([...contacts, { key: newContactKey(), name: "", is_primary: contacts.length === 0 }])
          }
        >
          <Plus className="size-4" aria-hidden /> Agregar contacto
        </Button>
      </div>
    </fieldset>
  );
}

/** Para el body de la API: sin la key local y con vacíos como null. */
export function contactsPayload(contacts: ContactDraft[], withPosition = false) {
  return contacts.map(({ name, position, email, phone, is_primary }) => ({
    name: name.trim(),
    ...(withPosition ? { position: position?.trim() || null } : {}),
    email: email?.trim() || null,
    phone: phone?.trim() || null,
    is_primary,
  }));
}
