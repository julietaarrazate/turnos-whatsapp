"use client";

import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { TextField } from "@/components/ui/field";
import { Notice } from "@/components/ui/notice";
import { api, errorMessage, unwrap } from "@/lib/api/client";

export function RequestPasswordReset() {
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setPending(true);
    setError(null);
    try {
      unwrap(await api.POST("/api/v1/auth/password-reset", { body: { email: String(form.get("email")) } }));
      setSent(true);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setPending(false);
    }
  }

  if (sent)
    return (
      <div className="flex flex-col gap-3">
        <h1 className="text-xl font-semibold">Revisá tu email</h1>
        <p className="text-sm text-ink-muted">
          Si el email está registrado, te mandamos un link para elegir una contraseña nueva. Vence en 60 minutos.
        </p>
        <Link href="/login" className="text-sm text-accent hover:underline">
          Volver a ingresar
        </Link>
      </div>
    );

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      <div>
        <h1 className="text-xl font-semibold">Recuperar contraseña</h1>
        <p className="mt-1 text-sm text-ink-muted">Te enviamos un link por email.</p>
      </div>
      {error ? <Notice tone="error">{error}</Notice> : null}
      <TextField label="Email" name="email" type="email" autoComplete="email" inputMode="email" required />
      <Button type="submit" size="lg" loading={pending}>
        Enviar link
      </Button>
      <Link href="/login" className="text-center text-sm text-accent hover:underline">
        Volver
      </Link>
    </form>
  );
}

export function ConfirmPasswordReset({ token }: { token: string }) {
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const password = String(form.get("password"));
    if (password !== String(form.get("confirm"))) {
      setError("Las contraseñas no coinciden");
      return;
    }
    setPending(true);
    setError(null);
    try {
      unwrap(await api.POST("/api/v1/auth/password-reset/confirm", { body: { token, password } }));
      setDone(true);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setPending(false);
    }
  }

  if (done)
    return (
      <div className="flex flex-col gap-3">
        <h1 className="text-xl font-semibold">Listo</h1>
        <p className="text-sm text-ink-muted">Tu contraseña cambió. Cerramos tus sesiones abiertas por seguridad.</p>
        <Link href="/login" className="text-sm text-accent hover:underline">
          Ingresar
        </Link>
      </div>
    );

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      <h1 className="text-xl font-semibold">Elegí una contraseña nueva</h1>
      {error ? <Notice tone="error">{error}</Notice> : null}
      <TextField label="Contraseña nueva" name="password" type="password" autoComplete="new-password" minLength={10} hint="Mínimo 10 caracteres." required />
      <TextField label="Repetila" name="confirm" type="password" autoComplete="new-password" required />
      <Button type="submit" size="lg" loading={pending}>
        Guardar
      </Button>
    </form>
  );
}
