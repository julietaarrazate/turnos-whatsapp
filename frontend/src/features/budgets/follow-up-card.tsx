"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import Link from "next/link";

import { api, unwrap } from "@/lib/api/client";
import { formatMoney } from "@/lib/format/number";

import { followUpText, PIPELINE_KEY } from "./budgets-list";

/** "Para seguir" en el inicio: propuestas sin decisión que conviene reactivar hoy. */
export function FollowUpCard() {
  const pipeline = useQuery({
    queryKey: [...PIPELINE_KEY, "follow-up"],
    queryFn: async () => unwrap(await api.GET("/api/v1/pipeline", { params: { query: { follow_up: true } } })),
  });
  const data = pipeline.data;
  if (!data) return null;
  return (
    <section aria-label="Para seguir" className="rounded-xl border border-line bg-surface">
      <div className="flex items-center justify-between border-b border-line px-4 py-3">
        <h2 className="font-semibold">Para seguir</h2>
        <Link href="/budgets" className="text-sm text-accent hover:underline">
          Ver presupuestos
        </Link>
      </div>
      {data.items.length === 0 ? (
        <p className="px-4 py-3 text-sm text-ink-muted">Nada pendiente: ninguna propuesta espera respuesta hace mucho.</p>
      ) : (
        <ul className="divide-y divide-line">
          {data.items.slice(0, 5).map((item) => (
            <li key={item.id}>
              <Link href={`/budgets/${item.id}`} className="flex items-center gap-3 px-4 py-3 hover:bg-subtle">
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">
                    {item.client_name} · {item.title}
                  </p>
                  <p className="truncate text-sm text-warning">{followUpText(item, data.follow_up_days)}</p>
                </div>
                <span className="font-medium tabular-nums">{formatMoney(item.sale_net)}</span>
                <ChevronRight className="size-4 text-ink-muted" aria-hidden />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
