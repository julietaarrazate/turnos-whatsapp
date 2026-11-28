"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Hourglass } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { HandieMark } from "@/components/brand/handie-logo";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api/client";

import { ME_QUERY_KEY } from "./session";

/** Se registró y su productora espera la aprobación de la dueña de la plataforma. */
export function PendingApproval({ organization }: { organization: string }) {
  const queryClient = useQueryClient();
  const router = useRouter();
  const [checking, setChecking] = useState(false);

  async function check() {
    setChecking(true);
    // Al aprobarla, la sesión tiene que pasar a la productora: se entra de nuevo con un refresh.
    await api.POST("/api/v1/auth/refresh");
    await queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY });
    setChecking(false);
  }

  async function logout() {
    await api.POST("/api/v1/auth/logout");
    queryClient.clear();
    router.replace("/login");
  }

  return (
    <main className="mx-auto flex min-h-dvh max-w-sm flex-col items-center justify-center gap-4 p-6 text-center">
      <HandieMark className="size-14" />
      <Hourglass className="size-6 text-ink-muted" aria-hidden />
      <h1 className="text-xl font-semibold">Tu cuenta está esperando aprobación</h1>
      <p className="text-sm text-ink-muted">
        Recibimos la cuenta de <strong className="text-ink">{organization}</strong>. La revisamos y te avisamos por mail
        cuando esté habilitada.
      </p>
      <Button variant="secondary" loading={checking} onClick={() => void check()}>
        Ya me avisaron, volver a revisar
      </Button>
      <button type="button" onClick={() => void logout()} className="text-sm text-ink-muted underline">
        Cerrar sesión
      </button>
    </main>
  );
}
