export const BUDGETS_KEY = ["budgets"] as const;
export const EVENTS_KEY = ["events"] as const;

export const budgetKey = (id: string) => [...BUDGETS_KEY, "detail", id] as const;
