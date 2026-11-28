"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { LockKeyhole } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { PasswordField, TextField } from "@/components/ui/field";
import { Notice } from "@/components/ui/notice";
import { ROLE_LABELS } from "@/features/auth/roles";
import { ME_QUERY_KEY, useSession } from "@/features/auth/session";
import { api, errorMessage, unwrap } from "@/lib/api/client";

const card = "flex max-w-xl flex-col gap-3 rounded-xl border border-line bg-surface p-5";

/** Nombre (el email es con el que se entra: no se cambia desde acá). */
export function ProfileForm() {
  const { me } = useSession();
  const queryClient = useQueryClient();
  const [name, setName] = useState(me.user.name);
  const save = useMutation({
    mutationFn: async () => unwrap(await api.PATCH("/api/v1/auth/me", { body: { name } })),
    onSuccess: (next) => queryClient.setQueryData(ME_QUERY_KEY, next),
  });
  return (
    <form
      aria-labelledby="profile-title"
      className={card}
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      <h2 id="profile-title" className="text-lg font-semibold">
        Datos de acceso
      </h2>
      <TextField label="Nombre" value={name} onChange={(e) => setName(e.currentTarget.value)} maxLength={200} autoComplete="name" />
      <TextField label="Email (para entrar)" value={me.user.email} readOnly disabled />
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" loading={save.isPending} disabled={name.trim() === me.user.name}>
          Guardar cambios
        </Button>
        <span className="text-sm text-ink-muted">Rol: {me.role ? ROLE_LABELS[me.role] : "—"}</span>
      </div>
      {save.isError ? <Notice tone="error">{errorMessage(save.error)}</Notice> : null}
      {save.isSuccess ? <Notice tone="success">Listo, guardado.</Notice> : null}
    </form>
  );
}

export function PasswordForm() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const change = useMutation({
    mutationFn: async () =>
      unwrap(await api.POST("/api/v1/auth/password", { body: { current_password: current, new_password: next } })),
    onSuccess: () => {
      setCurrent("");
      setNext("");
      setRepeat("");
    },
  });
  const mismatch = repeat.length > 0 && next !== repeat;
  return (
    <form
      aria-labelledby="password-title"
      className={card}
      onSubmit={(e) => {
        e.preventDefault();
        if (!mismatch) change.mutate();
      }}
    >
      <h2 id="password-title" className="text-lg font-semibold">
        Cambiar contraseña
      </h2>
      <PasswordField label="Contraseña actual" value={current} onChange={(e) => setCurrent(e.currentTarget.value)} autoComplete="current-password" required />
      <PasswordField
        label="Nueva contraseña"
        value={next}
        onChange={(e) => setNext(e.currentTarget.value)}
        autoComplete="new-password"
        minLength={10}
        hint="Al menos 10 caracteres."
        required
      />
      <PasswordField
        label="Repetí la nueva"
        value={repeat}
        onChange={(e) => setRepeat(e.currentTarget.value)}
        autoComplete="new-password"
        error={mismatch ? "No coincide con la nueva" : undefined}
        required
      />
      <div>
        <Button type="submit" variant="secondary" loading={change.isPending} disabled={!current || next.length < 10 || next !== repeat}>
          Cambiar contraseña
        </Button>
      </div>
      {change.isError ? <Notice tone="error">{errorMessage(change.error)}</Notice> : null}
      {change.isSuccess ? (
        <Notice tone="success">Listo. En los demás teléfonos y computadoras vas a tener que volver a entrar.</Notice>
      ) : null}
    </form>
  );
}

/** Dos casilleros de 4 números para elegir el PIN. */
function PinDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const queryClient = useQueryClient();
  const [pin, setPin] = useState("");
  const [repeat, setRepeat] = useState("");
  const save = useMutation({
    mutationFn: async () => unwrap(await api.PUT("/api/v1/auth/pin", { body: { pin } })),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY });
      onClose();
    },
  });
  useEffect(() => {
    if (open) dialog.current?.showModal();
    else dialog.current?.close();
  }, [open]);
  const digits = (value: string) => value.replace(/\D/g, "").slice(0, 4);
  const pinInput = "h-14 rounded-xl border border-line bg-surface text-center text-2xl tracking-[0.6em]";
  return (
    <dialog
      ref={dialog}
      aria-label="Configurar PIN"
      onClose={onClose}
      className="m-auto w-[min(24rem,calc(100%-2rem))] rounded-2xl border-0 bg-surface p-5 backdrop:bg-black/40"
    >
      <form
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <h2 className="text-lg font-bold">Configurar PIN</h2>
        <p className="text-sm text-ink-muted">Elegí 4 números. No uses 1234 ni tu año de nacimiento.</p>
        <label className="flex flex-col gap-1.5 text-sm font-medium">
          Nuevo PIN
          <input
            value={pin}
            onChange={(e) => setPin(digits(e.currentTarget.value))}
            type="password"
            inputMode="numeric"
            autoComplete="off"
            maxLength={4}
            className={pinInput}
          />
        </label>
        <label className="flex flex-col gap-1.5 text-sm font-medium">
          Repetí el PIN
          <input
            value={repeat}
            onChange={(e) => setRepeat(digits(e.currentTarget.value))}
            type="password"
            inputMode="numeric"
            autoComplete="off"
            maxLength={4}
            className={pinInput}
          />
        </label>
        {repeat.length === 4 && pin !== repeat ? <p className="text-sm text-danger">Los PIN no coinciden</p> : null}
        {save.isError ? <Notice tone="error">{errorMessage(save.error)}</Notice> : null}
        <div className="grid grid-cols-2 gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" loading={save.isPending} disabled={pin.length !== 4 || pin !== repeat}>
            Activar
          </Button>
        </div>
      </form>
    </dialog>
  );
}

/** Bloqueo con PIN: tapa la app al minimizarla o si queda quieta; la sesión sigue. */
export function PinSettings() {
  const { me } = useSession();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const enabled = me.pin_enabled ?? false;
  const remove = useMutation({
    mutationFn: async () => unwrap(await api.DELETE("/api/v1/auth/pin")),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY }),
  });
  return (
    <section aria-labelledby="pin-title" className={card}>
      <div className="flex items-start justify-between gap-2">
        <h2 id="pin-title" className="flex items-center gap-2 text-lg font-semibold">
          <LockKeyhole className="size-5 text-brand" aria-hidden /> Bloqueo con PIN
        </h2>
        <span className={enabled ? "rounded-md bg-success/15 px-2 py-0.5 text-xs font-bold text-success" : "rounded-md bg-subtle px-2 py-0.5 text-xs font-bold text-ink-muted"}>
          {enabled ? "Activado" : "Desactivado"}
        </span>
      </div>
      <p className="text-sm text-ink-muted">
        Pide un PIN de 4 números si minimizás la app más de un minuto o pasan 5 minutos sin usarla. La sesión se mantiene. Si el teléfono
        tiene huella o cara activada (más abajo), también sirve para destrabar.
      </p>
      <div className="flex flex-wrap gap-2">
        {enabled ? (
          <>
            <Button variant="secondary" onClick={() => setEditing(true)}>
              Cambiar PIN
            </Button>
            <Button
              variant="ghost"
              loading={remove.isPending}
              onClick={() => window.confirm("¿Desactivar el bloqueo con PIN?") && remove.mutate()}
            >
              Desactivar
            </Button>
          </>
        ) : (
          <Button onClick={() => setEditing(true)}>Activar bloqueo con PIN</Button>
        )}
      </div>
      {remove.isError ? <Notice tone="error">{errorMessage(remove.error)}</Notice> : null}
      <PinDialog open={editing} onClose={() => setEditing(false)} />
    </section>
  );
}
