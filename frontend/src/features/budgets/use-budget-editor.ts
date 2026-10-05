"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useRef, useState } from "react";

import { ApiError, api, errorMessage, unwrap } from "@/lib/api/client";
import type { Budget, LineUpdate, Schemas, VersionUpdate } from "@/lib/api/types";

import { BUDGETS_KEY, budgetKey } from "./keys";

type Mutation = (lock: string) => Promise<Budget>;

/**
 * Estado del editor. Las mutaciones se encolan (una a la vez, ARCHITECTURE §5.4) y cada una
 * manda el lock_version de la última respuesta: el autoguardado no genera 409 contra sí mismo.
 * Si otra pestaña o persona cambió el borrador, el 409 recarga y avisa.
 */
export function useBudgetEditor(budgetId: string) {
  const queryClient = useQueryClient();
  const key = budgetKey(budgetId);
  const budget = useQuery({
    queryKey: key,
    queryFn: async () => unwrap(await api.GET("/api/v1/budgets/{budget_id}", { params: { path: { budget_id: budgetId } } })),
  });
  const queue = useRef<Promise<unknown>>(Promise.resolve());
  const [pending, setPending] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);

  const run = useCallback(
    (mutation: Mutation): Promise<Budget | null> => {
      setPending((n) => n + 1);
      const next = queue.current.then(async () => {
        const current = queryClient.getQueryData<Budget>(key);
        try {
          const result = await mutation(String(current?.version.lock_version ?? 0));
          queryClient.setQueryData(key, result);
          void queryClient.invalidateQueries({ queryKey: [...BUDGETS_KEY, "list"] });
          setError(null);
          setConflict(false);
          return result;
        } catch (e) {
          if (e instanceof ApiError && e.code === "budget_version_conflict") {
            setConflict(true);
            await queryClient.invalidateQueries({ queryKey: key });
          } else {
            setError(errorMessage(e));
          }
          return null;
        } finally {
          setPending((n) => n - 1);
        }
      });
      queue.current = next.catch(() => undefined);
      return next;
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [queryClient, budgetId],
  );

  const path = { budget_id: budgetId };
  const ifMatch = (lock: string) => ({ "If-Match": lock });
  // Las mutaciones del borrador llevan el lock_version como header tipado (If-Match).

  return {
    budget,
    run,
    pending: pending > 0,
    error,
    conflict,
    clearError: () => setError(null),
    updateVersion: (body: VersionUpdate) =>
      run(async (lock) =>
        unwrap(await api.PATCH("/api/v1/budgets/{budget_id}/draft", { params: { path, header: ifMatch(lock) }, body })),
      ),
    addSection: (title: string) =>
      run(async (lock) =>
        unwrap(
          await api.POST("/api/v1/budgets/{budget_id}/draft/sections", {
            params: { path, header: ifMatch(lock) },
            body: { title_client: title },
          }),
        ),
      ),
    updateSection: (sectionId: string, body: Schemas["SectionUpdate"]) =>
      run(async (lock) =>
        unwrap(
          await api.PATCH("/api/v1/budgets/{budget_id}/draft/sections/{section_id}", {
            params: { path: { ...path, section_id: sectionId }, header: ifMatch(lock) },
            body,
          }),
        ),
      ),
    deleteSection: (sectionId: string) =>
      run(async (lock) =>
        unwrap(
          await api.DELETE("/api/v1/budgets/{budget_id}/draft/sections/{section_id}", {
            params: { path: { ...path, section_id: sectionId }, header: ifMatch(lock) },
          }),
        ),
      ),
    addLine: (body: Schemas["LineIn"]) => {
      const idempotencyKey = crypto.randomUUID();
      return run(async (lock) =>
        unwrap(
          await api.POST("/api/v1/budgets/{budget_id}/draft/lines", {
            params: { path, header: { ...ifMatch(lock), "Idempotency-Key": idempotencyKey } },
            body,
          }),
        ),
      );
    },
    updateLine: (lineId: string, body: LineUpdate) =>
      run(async (lock) =>
        unwrap(
          await api.PATCH("/api/v1/budgets/{budget_id}/draft/lines/{line_id}", {
            params: { path: { ...path, line_id: lineId }, header: ifMatch(lock) },
            body,
          }),
        ),
      ),
    deleteLine: (lineId: string) =>
      run(async (lock) =>
        unwrap(
          await api.DELETE("/api/v1/budgets/{budget_id}/draft/lines/{line_id}", {
            params: { path: { ...path, line_id: lineId }, header: ifMatch(lock) },
          }),
        ),
      ),
    freeze: (changeNote: string | null) =>
      run(async (lock) =>
        unwrap(
          await api.POST("/api/v1/budgets/{budget_id}/draft/freeze", {
            params: { path, header: ifMatch(lock) },
            body: { change_note: changeNote },
          }),
        ),
      ),
    newVersion: () =>
      run(async () => unwrap(await api.POST("/api/v1/budgets/{budget_id}/versions", { params: { path } }))),
    discardDraft: () =>
      run(async (lock) =>
        unwrap(await api.DELETE("/api/v1/budgets/{budget_id}/draft", { params: { path, header: ifMatch(lock) } })),
      ),
  };
}

export type BudgetEditor = ReturnType<typeof useBudgetEditor>;
