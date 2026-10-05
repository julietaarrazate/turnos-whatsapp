"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { TextField } from "@/components/ui/field";
import { Notice } from "@/components/ui/notice";
import { api, errorMessage, unwrap } from "@/lib/api/client";

/** Solo rutas internas: evita redirecciones abiertas con ?next=https://otro-sitio. */
function safeNext(value: string | null): string {
  return value && value.startsWith("/") && !value.startsWith("//") ? value : "/";
}

export function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setPending(true);
    setError(null);
    try {
      unwrap(
        await api.POST("/api/v1/auth/login", {
          body: { email: String(form.get("email")), password: String(form.get("password")) },
        }),
      );
      router.replace(safeNext(params.get("next")));
    } catch (err) {
      setError(errorMessage(err));
      setPending(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
      <div>
        <h1 className="text-xl font-semibold">Ingresar</h1>
        <p className="mt-1 text-sm text-ink-muted">Usá tu email y contraseña.</p>
      </div>
      {error ? <Notice tone="error">{error}</Notice> : null}
      <TextField label="Email" name="email" type="email" autoComplete="email" inputMode="email" required />
      <TextField label="Contraseña" name="password" type="password" autoComplete="current-password" required />
      <Button type="submit" size="lg" loading={pending}>
        Ingresar
      </Button>
      <Link href="/reset-password" className="text-center text-sm text-accent hover:underline">
        Olvidé mi contraseña
      </Link>
    </form>
  );
}
