"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Fingerprint, Trash2, X } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Notice } from "@/components/ui/notice";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import { formatDateTime } from "@/lib/format/date";

import {
  declinePasskey,
  forgetPasskeyHere,
  passkeyDeclined,
  passkeyHere,
  passkeysAvailable,
  registerPasskey,
  wasCancelled,
} from "./passkeys";

const KEY = ["passkeys"] as const;

function usePasskeys() {
  return useQuery({ queryKey: KEY, queryFn: async () => unwrap(await api.GET("/api/v1/auth/passkeys")) });
}

function useRegister(onDone?: () => void) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: registerPasskey,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: KEY });
      onDone?.();
    },
  });
}

/** Aviso, una sola vez por dispositivo: "la próxima entrá con tu huella". */
export function PasskeyOffer() {
  const [show, setShow] = useState(false);
  const [done, setDone] = useState(false);
  const register = useRegister(() => setDone(true));

  useEffect(() => {
    if (passkeyHere() || passkeyDeclined()) return;
    void passkeysAvailable().then(setShow);
  }, []);

  if (!show) return null;
  if (done) {
    return (
      <div className="mb-4">
        <Notice tone="success">Listo: la próxima vez entrás con tu huella o cara.</Notice>
      </div>
    );
  }
  return (
    <section aria-label="Entrar más rápido" className="mb-4 flex items-start gap-3 rounded-xl border border-line bg-surface p-3">
      <Fingerprint className="mt-0.5 size-6 shrink-0 text-brand" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="font-semibold">Entrá más rápido</p>
        <p className="text-sm text-ink-muted">
          Usá tu huella, tu cara o el bloqueo del teléfono en lugar del email y la contraseña.
        </p>
        <div className="mt-2 flex flex-wrap gap-2">
          <Button size="sm" loading={register.isPending} onClick={() => register.mutate()}>
            Activar
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              declinePasskey();
              setShow(false);
            }}
          >
            Ahora no
          </Button>
        </div>
        {register.isError && !wasCancelled(register.error) ? (
          <div className="mt-2">
            <Notice tone="error">{errorMessage(register.error)}</Notice>
          </div>
        ) : null}
      </div>
      <button
        type="button"
        aria-label="Cerrar el aviso"
        onClick={() => {
          declinePasskey();
          setShow(false);
        }}
        className="-mt-1 -mr-1 flex size-9 shrink-0 items-center justify-center rounded-full text-ink-muted hover:bg-subtle"
      >
        <X className="size-4" aria-hidden />
      </button>
    </section>
  );
}

/** "Mi cuenta": en qué dispositivos se puede entrar con huella, y sacar los que ya no van. */
export function PasskeySettings() {
  const passkeys = usePasskeys();
  const queryClient = useQueryClient();
  const [available, setAvailable] = useState(false);
  const register = useRegister();
  const remove = useMutation({
    mutationFn: async (id: string) => {
      unwrap(await api.DELETE("/api/v1/auth/passkeys/{passkey_id}", { params: { path: { passkey_id: id } } }));
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: KEY }),
  });

  useEffect(() => {
    void passkeysAvailable().then(setAvailable);
  }, []);

  return (
    <section aria-labelledby="passkeys-title" className="flex max-w-xl flex-col gap-3">
      <div>
        <h2 id="passkeys-title" className="text-lg font-semibold">
          Entrar con huella o cara
        </h2>
        <p className="text-sm text-ink-muted">
          En estos dispositivos entrás sin email ni contraseña. La huella o la cara nunca salen del teléfono: la app solo
          recibe la confirmación.
        </p>
      </div>
      {passkeys.isPending ? <p className="text-sm text-ink-muted">Cargando…</p> : null}
      {passkeys.isError ? <Notice tone="error">{errorMessage(passkeys.error)}</Notice> : null}
      {passkeys.data && passkeys.data.length === 0 ? (
        <p className="text-sm text-ink-muted">Todavía no activaste ningún dispositivo.</p>
      ) : null}
      {passkeys.data?.length ? (
        <ul className="divide-y divide-line rounded-xl border border-line bg-surface">
          {passkeys.data.map((passkey) => (
            <li key={passkey.id} className="flex items-center gap-3 px-3 py-2.5">
              <Fingerprint className="size-5 shrink-0 text-ink-muted" aria-hidden />
              <div className="min-w-0 flex-1">
                <p className="font-medium">{passkey.name}</p>
                <p className="text-xs text-ink-muted">
                  Activado {formatDateTime(passkey.created_at)}
                  {passkey.last_used_at ? ` · último uso ${formatDateTime(passkey.last_used_at)}` : ""}
                </p>
              </div>
              <button
                type="button"
                aria-label={`Quitar ${passkey.name}`}
                onClick={() => {
                  if (!window.confirm(`¿Quitar ${passkey.name}? Ahí vas a tener que entrar con email y contraseña.`)) return;
                  remove.mutate(passkey.id, { onSuccess: () => forgetPasskeyHere() });
                }}
                className="flex size-10 items-center justify-center rounded-full text-ink-muted hover:bg-subtle hover:text-danger"
              >
                <Trash2 className="size-4" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      {remove.isError ? <Notice tone="error">{errorMessage(remove.error)}</Notice> : null}
      {available ? (
        <div>
          <Button variant="secondary" loading={register.isPending} onClick={() => register.mutate()}>
            <Fingerprint className="size-4" aria-hidden /> Activar en este dispositivo
          </Button>
        </div>
      ) : (
        <p className="text-sm text-ink-muted">Este navegador no permite entrar con huella o cara.</p>
      )}
      {register.isError && !wasCancelled(register.error) ? <Notice tone="error">{errorMessage(register.error)}</Notice> : null}
      {register.isSuccess ? <Notice tone="success">Listo: este dispositivo ya puede entrar con huella o cara.</Notice> : null}
    </section>
  );
}
