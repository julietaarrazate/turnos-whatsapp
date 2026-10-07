"use client";

import { ArrowLeft, ChevronDown, ChevronUp, FileSpreadsheet, Lock, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Notice } from "@/components/ui/notice";
import { useSession } from "@/features/auth/session";
import { EventStatusBadge } from "@/features/events/status";
import { pct } from "@/features/pricing/shared";
import type { Budget, BudgetLine, BudgetSection, BudgetVersion } from "@/lib/api/types";
import { formatDate } from "@/lib/format/date";
import { formatMoney } from "@/lib/format/number";

import { CommitField } from "./commit-field";
import { daysField, quantityField } from "./format";
import { LineDetail } from "./line-detail";
import { ProductSearch } from "./product-search";
import { ProposalsPanel } from "@/features/proposals/proposals-panel";

import { CostsBanner, ReapplyRules } from "./refresh-dialogs";
import { TotalsFooter } from "./totals";
import { type BudgetEditor as Editor, useBudgetEditor } from "./use-budget-editor";
import { VersionSettings } from "./version-settings";

function LineRow({
  line,
  editable,
  editor,
  onOpen,
}: {
  line: BudgetLine;
  editable: boolean;
  editor: Editor;
  onOpen: () => void;
}) {
  const stale = line.cost?.cost_stale;
  return (
    <li className="grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-2 px-4 py-3 lg:grid-cols-[minmax(0,1fr)_6rem_4.5rem_8rem_5rem_8rem]">
      <button type="button" onClick={onOpen} className="min-w-0 text-left" aria-label={`Abrir ${line.name_internal}`}>
        <span className="flex items-center gap-1.5 truncate font-medium">
          {line.name_internal}
          {line.is_locked ? <Lock className="size-3.5 shrink-0 text-ink-muted" aria-label="Bloqueada" /> : null}
        </span>
        <span className="block truncate text-xs text-ink-muted">
          {[line.supplier_name, line.category_name].filter(Boolean).join(" · ") || "Ítem libre"}
          {stale ? <span className="text-warning"> · costo de hace {line.cost?.cost_days_old} días</span> : null}
          {!line.show_on_proposal ? " · oculto en la propuesta" : null}
        </span>
      </button>
      <span className="text-right font-medium tabular-nums lg:order-last">{formatMoney(line.sale_total)}</span>
      <div className="col-span-2 flex items-center gap-2 lg:contents">
        <CommitField
          label={`Cantidad de ${line.name_internal}`}
          value={line.quantity}
          {...quantityField}
          disabled={!editable}
          className="w-24 lg:w-auto"
          suffix={line.unit_code}
          onCommit={(quantity) => void editor.updateLine(line.id, { quantity })}
        />
        {line.charge_mode === "PER_DAY" ? (
          <CommitField
            label={`Días de ${line.name_internal}`}
            value={line.days}
            {...daysField}
            inputMode="numeric"
            disabled={!editable}
            className="w-16 lg:w-auto"
            suffix="d"
            onCommit={(days) => void editor.updateLine(line.id, { days })}
          />
        ) : (
          <span className="hidden text-center text-xs text-ink-muted lg:block">—</span>
        )}
        <span className="flex-1 text-right text-xs text-ink-muted tabular-nums lg:text-sm">
          {line.cost ? formatMoney(line.cost.cost_total) : null}
        </span>
        <span className="w-14 text-right text-xs text-ink-muted tabular-nums lg:w-auto lg:text-sm">
          {line.margin?.markup_applied ? pct(line.margin.markup_applied) : line.margin ? "—" : null}
        </span>
      </div>
    </li>
  );
}

function SectionBlock({
  section,
  index,
  count,
  version,
  editable,
  editor,
  onOpenLine,
}: {
  section: BudgetSection;
  index: number;
  count: number;
  version: BudgetVersion;
  editable: boolean;
  editor: Editor;
  onOpenLine: (id: string) => void;
}) {
  const showCost = Boolean(version.costs);
  const showMargin = Boolean(version.margins);
  return (
    <section aria-label={`Sección ${section.title_client}`} className="mb-4 rounded-xl border border-line bg-surface">
      <header className="flex items-center gap-2 border-b border-line px-4 py-2">
        {editable ? (
          <CommitField
            label="Nombre de la sección"
            value={section.title_client}
            display={(v) => v}
            parse={(t) => (t.trim() ? t.trim() : undefined)}
            inputMode="text"
            className="flex-1 [&_input]:border-transparent [&_input]:text-left [&_input]:font-semibold"
            onCommit={(title_client) => void editor.updateSection(section.id, { title_client })}
          />
        ) : (
          <h2 className="flex-1 font-semibold">{section.title_client}</h2>
        )}
        <span className="text-sm font-medium tabular-nums">{formatMoney(section.sale_total)}</span>
        {editable ? (
          <span className="flex">
            <button
              type="button"
              aria-label="Subir sección"
              disabled={index === 0}
              onClick={() => void editor.updateSection(section.id, { position: index - 1 })}
              className="rounded p-1 text-ink-muted hover:bg-subtle disabled:opacity-30"
            >
              <ChevronUp className="size-4" aria-hidden />
            </button>
            <button
              type="button"
              aria-label="Bajar sección"
              disabled={index === count - 1}
              onClick={() => void editor.updateSection(section.id, { position: index + 1 })}
              className="rounded p-1 text-ink-muted hover:bg-subtle disabled:opacity-30"
            >
              <ChevronDown className="size-4" aria-hidden />
            </button>
            {count > 1 ? (
              <button
                type="button"
                aria-label={`Borrar sección ${section.title_client}`}
                onClick={() => {
                  if (section.lines.length === 0 || window.confirm(`¿Borrar "${section.title_client}" y sus ${section.lines.length} ítems?`)) {
                    void editor.deleteSection(section.id);
                  }
                }}
                className="rounded p-1 text-ink-muted hover:bg-subtle"
              >
                <Trash2 className="size-4" aria-hidden />
              </button>
            ) : null}
          </span>
        ) : null}
      </header>
      {section.lines.length ? (
        <>
          <div className="hidden px-4 pt-2 text-[11px] uppercase tracking-wide text-ink-muted lg:grid lg:grid-cols-[minmax(0,1fr)_6rem_4.5rem_8rem_5rem_8rem] lg:gap-x-3">
            <span>Ítem</span>
            <span className="text-right">Cantidad</span>
            <span className="text-right">Días</span>
            <span className="text-right">{showCost ? "Costo" : ""}</span>
            <span className="text-right">{showMargin ? "Markup" : ""}</span>
            <span className="text-right">Venta</span>
          </div>
          <ul className="divide-y divide-line">
            {section.lines.map((line) => (
              <LineRow key={line.id} line={line} editable={editable} editor={editor} onOpen={() => onOpenLine(line.id)} />
            ))}
          </ul>
        </>
      ) : (
        <p className="px-4 py-3 text-sm text-ink-muted">Sin ítems todavía.</p>
      )}
      {editable ? (
        <div className="border-t border-line px-4 py-3">
          <ProductSearch
            onPick={(product) => void editor.addLine({ section_id: section.id, product_id: product.id })}
            onPackage={(pkg) => void editor.addPackage({ package_id: pkg.id, section_id: section.id })}
            onFree={(name) => void editor.addLine({ section_id: section.id, name })}
          />
        </div>
      ) : null}
    </section>
  );
}

function VersionBar({ budget, editor, editable }: { budget: Budget; editor: Editor; editable: boolean }) {
  const version = budget.version;
  const hasDraft = budget.versions.some((v) => v.status === "DRAFT");
  const [freezing, setFreezing] = useState(false);
  const [note, setNote] = useState("");
  return (
    <div className="mb-4 flex flex-wrap items-center gap-2 text-sm">
      {budget.versions.map((v) => (
        <span
          key={v.id}
          className={`rounded-full border px-2.5 py-0.5 ${v.id === version.id ? "border-accent bg-accent/10 text-accent" : "border-line text-ink-muted"}`}
          title={v.change_note ?? undefined}
        >
          v{v.version_no} {v.status === "DRAFT" ? "· borrador" : `· ${formatDate(v.frozen_at ?? v.updated_at)}`}
        </span>
      ))}
      {budget.versions.length > 1 ? (
        <Link
          href={`/budgets/${budget.id}/compare?from=${budget.versions[budget.versions.length - 2].version_no}&to=${budget.versions[budget.versions.length - 1].version_no}`}
          className="text-accent hover:underline"
        >
          Comparar
        </Link>
      ) : null}
      <span className="flex-1" />
      {editable && version.status === "DRAFT" && !freezing ? (
        <>
          <ReapplyRules budget={budget} editor={editor} />
          {budget.versions.length > 1 ? (
            <Button variant="ghost" size="sm" onClick={() => window.confirm("¿Descartar los cambios del borrador?") && void editor.discardDraft()}>
              Descartar borrador
            </Button>
          ) : null}
          <Button variant="secondary" size="sm" onClick={() => setFreezing(true)}>
            Guardar versión
          </Button>
        </>
      ) : null}
      <a
        href={`/api/v1/budgets/${budget.id}/versions/${budget.version.version_no}/export.xlsx`}
        className="inline-flex h-8 items-center gap-1 px-3 text-sm text-ink hover:underline"
      >
        <FileSpreadsheet className="size-4" aria-hidden /> Excel
      </a>
      {editable ? (
        <Link href={`/budgets/new?from=${budget.id}`} className="inline-flex h-8 items-center px-3 text-sm text-ink hover:underline">
          Duplicar para otro evento
        </Link>
      ) : null}
      {editable && !hasDraft ? (
        <Button size="sm" onClick={() => void editor.newVersion()}>
          <Plus className="size-4" aria-hidden /> Nueva versión
        </Button>
      ) : null}
      {freezing ? (
        <form
          aria-label="Guardar versión"
          className="flex w-full flex-wrap items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void editor.freeze(note.trim() || null).then(() => setFreezing(false));
          }}
        >
          <input
            autoFocus
            value={note}
            maxLength={2000}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Qué cambió (opcional): ej. bajamos iluminación"
            aria-label="Nota de la versión"
            className="h-10 min-w-0 flex-1 rounded-lg border border-line bg-surface px-3 text-base sm:text-sm"
          />
          <Button type="submit" size="sm">
            Guardar v{version.version_no}
          </Button>
          <Button type="button" variant="ghost" size="sm" onClick={() => setFreezing(false)}>
            Cancelar
          </Button>
        </form>
      ) : null}
    </div>
  );
}

export function BudgetEditor({ budgetId, copied }: { budgetId: string; copied?: { costs: number; rules: number } }) {
  const { can } = useSession();
  const editor = useBudgetEditor(budgetId);
  const [openLine, setOpenLine] = useState<string | null>(null);
  const budget = editor.budget.data;

  if (editor.budget.isPending) return <p className="text-sm text-ink-muted">Cargando…</p>;
  if (editor.budget.isError || !budget) return <Notice tone="error">No pudimos abrir el presupuesto.</Notice>;

  const version = budget.version;
  const editable = can("budget.edit") && version.status === "DRAFT";
  const line = openLine
    ? version.sections.flatMap((s) => s.lines).find((l) => l.id === openLine)
    : undefined;

  return (
    <div className="pb-4">
      <Link href="/budgets" className="mb-3 inline-flex items-center gap-1 text-sm text-ink-muted hover:text-ink">
        <ArrowLeft className="size-4" aria-hidden /> Presupuestos
      </Link>
      <header className="mb-4">
        <h1 className="text-xl font-semibold tracking-tight sm:text-2xl">
          #{budget.number} · {budget.title}
        </h1>
        <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-ink-muted">
          <Link href={`/clients/${budget.event.client_id}`} className="hover:underline">
            {budget.event.client_name}
          </Link>
          ·
          <Link href={`/events/${budget.event.id}`} className="hover:underline">
            Evento #{budget.event.number}
          </Link>
          {budget.event.start_date ? `· ${formatDate(budget.event.start_date)}` : "· fecha a confirmar"}
          {budget.event.event_days > 1 ? `· ${budget.event.event_days} días` : null}
          <EventStatusBadge status={budget.event.status} />
        </p>
      </header>

      <VersionBar budget={budget} editor={editor} editable={can("budget.edit")} />
      {copied ? (
        <div className="mb-4">
          <Notice tone="success">
            Presupuesto duplicado con los valores de hoy:{" "}
            {copied.costs === 0 && copied.rules === 0
              ? "costos y markups iguales al original."
              : `${copied.costs} ${copied.costs === 1 ? "costo actualizado" : "costos actualizados"} y ${copied.rules} ${copied.rules === 1 ? "markup distinto" : "markups distintos"} respecto del original.`}
          </Notice>
        </div>
      ) : null}
      <CostsBanner budget={budget} editor={editor} />
      {version.status === "FROZEN" ? (
        <div className="mb-4">
          <Notice>
            Versión {version.version_no} guardada{version.change_note ? `: ${version.change_note}` : ""}. No se modifica; para cambiar algo, creá una nueva versión.
          </Notice>
        </div>
      ) : null}
      {editor.conflict ? (
        <div className="mb-4">
          <Notice tone="error">
            Alguien más cambió este presupuesto mientras lo editabas. Recargamos la última versión: revisá y volvé a hacer el cambio.
          </Notice>
        </div>
      ) : null}
      {editor.error ? (
        <div className="mb-4">
          <Notice tone="error">{editor.error}</Notice>
        </div>
      ) : null}

      <ProposalsPanel budget={budget} editor={editor} />

      <VersionSettings budget={budget} version={version} editable={editable} onUpdate={(body) => void editor.updateVersion(body)} />

      {version.sections.map((section, index) => (
        <SectionBlock
          key={section.id}
          section={section}
          index={index}
          count={version.sections.length}
          version={version}
          editable={editable}
          editor={editor}
          onOpenLine={setOpenLine}
        />
      ))}
      {editable ? (
        <Button variant="secondary" onClick={() => void editor.addSection("Nueva sección")}>
          <Plus className="size-4" aria-hidden /> Agregar sección
        </Button>
      ) : null}

      <TotalsFooter version={version} pending={editor.pending} />

      {line ? (
        <LineDetail
          key={line.id}
          line={line}
          version={version}
          editable={editable}
          onClose={() => setOpenLine(null)}
          onUpdate={(body) => void editor.updateLine(line.id, body)}
          onDelete={() => void editor.deleteLine(line.id)}
        />
      ) : null}
    </div>
  );
}
