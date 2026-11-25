"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { PasswordField, TextField } from "@/components/ui/field";
import { Notice } from "@/components/ui/notice";
import { api, errorMessage, unwrap } from "@/lib/api/client";

import { ROLE_LABELS } from "./roles";

export function AcceptInvitation({ token }: { token: string }) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const preview = useQuery({
    queryKey: ["invitation", token],
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/auth/invitations/{token}", { params: { path: { token } } })),
  });

  if (preview.isPending) return <p className="text-sm text-ink-muted">Cargando invitación…</p>;
  if (preview.isError)
    return (
      <div className="flex flex-col gap-3">
        <h1 className="text-xl font-semibold">Invitación no válida</h1>
        <Notice tone="error">{errorMessage(preview.error)}</Notice>
        <p className="text-sm text-ink-muted">Pedile a quien te invitó que te envíe una nueva.</p>
      </div>
    );

  const invitation = preview.data;

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setPending(true);
    setError(null);
    try {
      unwrap(
        await api.POST("/api/v1/auth/invitations/accept", {
          body: {
            token,
            password: String(form.get("password")),
            name: invitation.user_exists ? null : String(form.get("name")),
          },
        }),
      );
      router.replace("/");
    } catch (err) {
      setError(errorMessage(err));
      setPending(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      <div>
        <h1 className="text-xl font-semibold">Sumate a {invitation.organization_name}</h1>
        <p className="mt-1 text-sm text-ink-muted">
          Invitación para <strong>{invitation.email}</strong> como {ROLE_LABELS[invitation.role]}.
        </p>
      </div>
      {error ? <Notice tone="error">{error}</Notice> : null}
      {invitation.user_exists ? (
        <PasswordField label="Tu contraseña actual" name="password" autoComplete="current-password" required />
      ) : (
        <>
          <TextField label="Nombre y apellido" name="name" autoComplete="name" required />
          <PasswordField
            label="Elegí una contraseña"
            name="password"
            autoComplete="new-password"
            minLength={10}
            hint="Mínimo 10 caracteres."
            required
          />
        </>
      )}
      <Button type="submit" size="lg" loading={pending}>
        Aceptar invitación
      </Button>
    </form>
  );
}
