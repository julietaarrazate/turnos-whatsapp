"use client";

import { useInfiniteQuery } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { Notice } from "@/components/ui/notice";
import { PageHeader } from "@/components/ui/page-header";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import { formatDateTime } from "@/lib/format/date";

const ACTION_LABELS: Record<string, string> = {
  "org.settings_changed": "Cambió la configuración de la organización",
  "org.fiscal_changed": "Cambió los datos fiscales",
  "membership.invited": "Invitó a una persona",
  "membership.joined": "Se sumó a la organización",
  "membership.changed": "Cambió el rol de una persona",
  "membership.disabled": "Desactivó a una persona",
  "invitation.revoked": "Anuló una invitación",
};

function describeChange(value: Record<string, unknown> | null): string {
  if (!value) return "";
  return Object.entries(value)
    .map(([key, v]) => `${key}: ${String(v)}`)
    .join(" · ");
}

export function AuditLog() {
  const logs = useInfiniteQuery({
    queryKey: ["audit-logs"],
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam }) =>
      unwrap(await api.GET("/api/v1/audit-logs", { params: { query: { before: pageParam, limit: 50 } } })),
    getNextPageParam: (page) => page.next_cursor ?? null,
  });

  return (
    <>
      <PageHeader title="Auditoría" description="Registro inalterable de los cambios importantes." />
      {logs.isError ? <Notice tone="error">{errorMessage(logs.error)}</Notice> : null}
      <section className="rounded-xl border border-line bg-surface px-5">
        <ul className="divide-y divide-line">
          {logs.data?.pages.flatMap((page) =>
            page.items.map((entry) => (
              <li key={entry.id} className="py-3 text-sm">
                <p className="font-medium">{ACTION_LABELS[entry.action] ?? entry.action}</p>
                <p className="text-ink-muted">
                  {formatDateTime(entry.created_at)}
                  {entry.after ? ` · ${describeChange(entry.after)}` : ""}
                </p>
              </li>
            )),
          )}
        </ul>
        {logs.data && logs.data.pages[0].items.length === 0 ? (
          <p className="py-4 text-sm text-ink-muted">Todavía no hay actividad registrada.</p>
        ) : null}
      </section>
      {logs.hasNextPage ? (
        <div className="mt-4 flex justify-center">
          <Button variant="secondary" loading={logs.isFetchingNextPage} onClick={() => logs.fetchNextPage()}>
            Ver más
          </Button>
        </div>
      ) : null}
    </>
  );
}
