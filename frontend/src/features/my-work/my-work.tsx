"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Notice } from "@/components/ui/notice";
import { EVENTS_KEY } from "@/features/budgets/keys";
import { PIECE_AREA, PIECE_STATUS } from "@/features/events/event-pieces";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import type { Schemas } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatDay } from "@/lib/format/date";

type MyPiece = Schemas["MyPiece"];
type MyTask = Schemas["MyTask"];
type WorkEvent = Schemas["WorkEvent"];
type PieceStatus = Schemas["PieceStatus"];
type TaskStatus = Schemas["TaskStatus"];

export const MY_WORK_KEY = ["my-work"] as const;
const PHASES = Object.keys(PIECE_STATUS) as PieceStatus[];

function eventLine(event: WorkEvent): string {
  const mount = event.mount_date ? `Montaje ${formatDay(event.mount_date)}` : "Montaje a confirmar";
  return `#${event.number} ${event.name} · ${mount}`;
}

function dueLine(due: string | null, late: boolean): string | null {
  if (!due) return null;
  return late ? `Atrasada · vencía ${formatDay(due)}` : `Vence ${formatDay(due)}`;
}

/** Al mover algo propio, se refresca la lista y lo que ve producción en el evento. */
function useMove<Body>(mutationFn: (body: Body) => Promise<unknown>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSettled: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: MY_WORK_KEY }),
        queryClient.invalidateQueries({ queryKey: EVENTS_KEY }),
      ]),
  });
}

function PieceCard({ piece }: { piece: MyPiece }) {
  const move = useMove(async (status: PieceStatus) =>
    unwrap(await api.PATCH("/api/v1/my-work/pieces/{piece_id}", { params: { path: { piece_id: piece.id } }, body: { status } })),
  );
  // Optimista: el botón tocado se marca al instante.
  const current = move.isPending && move.variables ? move.variables : piece.status;
  const due = dueLine(piece.due_date, piece.late);
  return (
    <li>
      <article aria-label={piece.name} className="flex flex-col gap-3 rounded-2xl border border-line bg-surface p-4">
        <header>
          <p className="text-xs font-semibold text-ink-muted">{eventLine(piece.event)}</p>
          <h3 className="text-lg leading-tight font-bold">{piece.name}</h3>
          <p className="text-sm text-ink-muted">{PIECE_AREA[piece.area]}</p>
          {due ? <p className={cn("text-sm", piece.late ? "font-bold text-danger" : "text-ink-muted")}>{due}</p> : null}
          {piece.notes ? <p className="mt-1 text-sm whitespace-pre-line">{piece.notes}</p> : null}
        </header>
        <div role="group" aria-label={`Estado de ${piece.name}`} className="grid grid-cols-5 gap-1.5">
          {PHASES.map((phase) => {
            const on = phase === current;
            return (
              <button
                key={phase}
                type="button"
                aria-pressed={on}
                disabled={move.isPending}
                onClick={() => move.mutate(phase)}
                className={cn(
                  "h-14 rounded-xl px-1 text-xs leading-tight font-bold",
                  on ? cn(PIECE_STATUS[phase].tone, "ring-2 ring-ink") : "border border-line bg-surface text-ink-muted",
                )}
              >
                {PIECE_STATUS[phase].short}
              </button>
            );
          })}
        </div>
        {move.isError ? <Notice tone="error">{errorMessage(move.error)}</Notice> : null}
      </article>
    </li>
  );
}

const TASK_ACTIONS: { status: TaskStatus; label: string }[] = [
  { status: "IN_PROGRESS", label: "En curso" },
  { status: "DONE", label: "Hecha" },
];

function TaskCard({ task }: { task: MyTask }) {
  const move = useMove(async (status: TaskStatus) =>
    unwrap(await api.PATCH("/api/v1/my-work/tasks/{task_id}", { params: { path: { task_id: task.id } }, body: { status } })),
  );
  const current = move.isPending && move.variables ? move.variables : task.status;
  const due = dueLine(task.due_date, task.late);
  return (
    <li>
      <article aria-label={task.title} className="flex flex-col gap-3 rounded-2xl border border-line bg-surface p-4">
        <header>
          <p className="text-xs font-semibold text-ink-muted">{eventLine(task.event)}</p>
          <h3 className="text-lg leading-tight font-bold">{task.title}</h3>
          {due ? <p className={cn("text-sm", task.late ? "font-bold text-danger" : "text-ink-muted")}>{due}</p> : null}
        </header>
        <div className="grid grid-cols-2 gap-2">
          {TASK_ACTIONS.map(({ status, label }) => (
            <button
              key={status}
              type="button"
              aria-label={`${task.title}: ${label}`}
              aria-pressed={current === status}
              disabled={move.isPending}
              onClick={() => move.mutate(status)}
              className={cn(
                "h-14 rounded-xl text-base font-bold",
                status === "DONE" ? "bg-magenta text-white" : "border border-line bg-surface text-ink",
                current === status && "ring-2 ring-ink",
              )}
            >
              {label}
            </button>
          ))}
        </div>
        {move.isError ? <Notice tone="error">{errorMessage(move.error)}</Notice> : null}
      </article>
    </li>
  );
}

export function MyWork() {
  const query = useQuery({
    queryKey: MY_WORK_KEY,
    queryFn: async () => unwrap(await api.GET("/api/v1/my-work")),
  });
  if (query.isPending) return <p className="text-sm text-ink-muted">Cargando…</p>;
  if (query.isError) return <Notice tone="error">{errorMessage(query.error)}</Notice>;
  const { pieces, tasks } = query.data;
  const late = [...pieces, ...tasks].filter((item) => item.late).length;

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">Mis tareas</h1>
        <p className={cn("mt-1 text-sm", late ? "font-bold text-danger" : "text-ink-muted")}>
          {pieces.length + tasks.length === 0
            ? "No tenés nada pendiente. ¡Todo al día!"
            : late
              ? `${late} ${late === 1 ? "atrasada" : "atrasadas"}: arrancá por ahí.`
              : "Tocá el estado para avisar en qué está cada cosa."}
        </p>
      </header>
      {pieces.length ? (
        <section aria-label="Mis piezas" className="flex flex-col gap-2">
          <h2 className="font-semibold">
            Piezas <span className="font-normal text-ink-muted">· {pieces.length}</span>
          </h2>
          <ul className="flex flex-col gap-3">
            {pieces.map((piece) => (
              <PieceCard key={piece.id} piece={piece} />
            ))}
          </ul>
        </section>
      ) : null}
      {tasks.length ? (
        <section aria-label="Mis tareas pendientes" className="flex flex-col gap-2">
          <h2 className="font-semibold">
            Tareas <span className="font-normal text-ink-muted">· {tasks.length}</span>
          </h2>
          <ul className="flex flex-col gap-3">
            {tasks.map((task) => (
              <TaskCard key={task.id} task={task} />
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
