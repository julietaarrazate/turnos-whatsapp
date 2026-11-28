"use client";

import Link from "next/link";

import { Notice } from "@/components/ui/notice";
import { PendingApproval } from "@/features/auth/pending-approval";
import { SessionProvider, useMeQuery } from "@/features/auth/session";
import { AppShell } from "@/features/shell/app-shell";
import { errorMessage } from "@/lib/api/client";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const me = useMeQuery();

  if (me.isPending) {
    return (
      <div className="flex min-h-dvh items-center justify-center" aria-busy>
        <span className="size-6 animate-spin rounded-full border-2 border-accent border-t-transparent" />
      </div>
    );
  }
  if (me.isError) {
    return (
      <div className="mx-auto max-w-sm p-6">
        <Notice tone="error">{errorMessage(me.error)}</Notice>
      </div>
    );
  }
  if (me.data.active_organization_id === null && me.data.pending_organization) {
    return <PendingApproval organization={me.data.pending_organization} />;
  }
  if (me.data.active_organization_id === null) {
    return (
      <div className="mx-auto max-w-sm p-6">
        <Notice>
          Tu usuario no tiene ninguna organización activa: puede que no te hayan invitado todavía o que el acceso
          esté pausado. Escribile a quien te dio acceso a Handie.
        </Notice>
        {me.data.platform_admin ? (
          <Link href="/admin" className="mt-4 block text-center text-sm font-semibold text-brand underline">
            Ir al panel de administración
          </Link>
        ) : null}
      </div>
    );
  }
  return (
    <SessionProvider me={me.data}>
      <AppShell>{children}</AppShell>
    </SessionProvider>
  );
}
