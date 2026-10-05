"use client";

import { Notice } from "@/components/ui/notice";
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
  if (me.data.active_organization_id === null) {
    return (
      <div className="mx-auto max-w-sm p-6">
        <Notice>
          Tu usuario no pertenece a ninguna organización activa. Pedí una invitación a quien administre la tuya.
        </Notice>
      </div>
    );
  }
  return (
    <SessionProvider me={me.data}>
      <AppShell>{children}</AppShell>
    </SessionProvider>
  );
}
