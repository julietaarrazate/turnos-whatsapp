"use client";

import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { Notice } from "@/components/ui/notice";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import { formatDate } from "@/lib/format/date";

import { SECTIONS } from "./event-files";

const LABEL: Record<string, string> = Object.fromEntries(SECTIONS.map((s) => [s.key, s.label]));

/** "Archivos": buscar en todos los eventos ("logo Natura", "plano mostrador"). */
export function FilesSearch() {
  const [text, setText] = useState("");
  const [q, setQ] = useState("");
  useEffect(() => {
    const timer = window.setTimeout(() => setQ(text.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [text]);
  const results = useQuery({
    queryKey: ["files", "search", q],
    enabled: q.length >= 2,
    queryFn: async () => unwrap(await api.GET("/api/v1/files/search", { params: { query: { q } } })),
  });
  return (
    <div className="flex flex-col gap-4">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">Archivos</h1>
        <p className="mt-1 text-sm text-ink-muted">Buscá por nombre del archivo, de la pieza o del evento. Cada archivo vive en su evento.</p>
      </header>
      <label className="flex h-12 items-center gap-2 rounded-xl border border-line bg-surface px-3 focus-within:outline-2 focus-within:outline-accent">
        <Search className="size-5 text-ink-muted" aria-hidden />
        <input
          type="search"
          value={text}
          onChange={(e) => setText(e.currentTarget.value)}
          aria-label="Buscar archivos"
          placeholder="Ej.: logo Natura, plano mostrador"
          className="h-full min-w-0 flex-1 bg-transparent text-base outline-none"
        />
      </label>
      {results.isError ? <Notice tone="error">{errorMessage(results.error)}</Notice> : null}
      {q.length >= 2 && results.data?.length === 0 ? <p className="text-sm text-ink-muted">No encontramos nada con “{q}”.</p> : null}
      {results.data?.length ? (
        <section aria-label="Resultados" className="rounded-xl border border-line bg-surface px-4">
          <ul className="divide-y divide-line">
            {results.data.map((item) => (
              <li key={`${item.source}-${item.id}`} className="flex flex-col gap-0.5 py-2.5">
                <a href={item.href} target="_blank" rel="noopener noreferrer" className="font-semibold text-ink hover:underline">
                  {item.title}
                  {item.version ? <span className="ml-1.5 text-xs font-bold text-success">v{item.version}</span> : null}
                </a>
                <span className="text-xs text-ink-muted">
                  <Link href={`/events/${item.event.id}/files`} className="hover:underline">
                    #{item.event.number} {item.event.name}
                  </Link>
                  {" · "}
                  {[LABEL[item.category], item.piece_name, formatDate(item.created_at)].filter(Boolean).join(" · ")}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
