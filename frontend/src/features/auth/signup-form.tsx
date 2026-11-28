"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { PasswordField, TextField } from "@/components/ui/field";
import { Notice } from "@/components/ui/notice";
import { api, errorMessage, unwrap } from "@/lib/api/client";

import { ME_QUERY_KEY } from "./session";

export function SignupForm() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setPending(true);
    setError(null);
    try {
      const me = unwrap(
        await api.POST("/api/v1/auth/signup", {
          body: {
            name: String(form.get("name")),
            organization_name: String(form.get("organization_name")),
            email: String(form.get("email")),
            password: String(form.get("password")),
            website: String(form.get("website") ?? ""),
          },
        }),
      );
      queryClient.setQueryData(ME_QUERY_KEY, me);
      router.replace("/");
    } catch (err) {
      setError(errorMessage(err));
      setPending(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
      <div>
        <h1 className="text-xl font-semibold">Crear cuenta</h1>
        <p className="mt-1 text-sm text-ink-muted">
          Armá tu usuario y el de tu productora. Revisamos cada cuenta nueva antes de habilitarla.
        </p>
      </div>
      {error ? <Notice tone="error">{error}</Notice> : null}
      <TextField label="Nombre y apellido" name="name" autoComplete="name" required maxLength={200} />
      <TextField
        label="Nombre de tu productora"
        name="organization_name"
        autoComplete="organization"
        required
        maxLength={200}
      />
      <TextField label="Email" name="email" type="email" autoComplete="email" inputMode="email" required />
      <PasswordField
        label="Elegí una contraseña"
        name="password"
        autoComplete="new-password"
        minLength={10}
        hint="Mínimo 10 caracteres."
        required
      />
      {/* Campo trampa: invisible para las personas, los robots lo completan. */}
      <div aria-hidden className="absolute -left-[9999px] h-0 w-0 overflow-hidden">
        <label>
          Sitio web
          <input name="website" type="text" tabIndex={-1} autoComplete="off" />
        </label>
      </div>
      <Button type="submit" size="lg" loading={pending}>
        Crear cuenta
      </Button>
      <p className="text-center text-sm text-ink-muted">
        ¿Ya tenés cuenta?{" "}
        <Link href="/login" className="text-accent hover:underline">
          Ingresar
        </Link>
      </p>
    </form>
  );
}
