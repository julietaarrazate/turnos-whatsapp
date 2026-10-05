import { Suspense } from "react";

import { NewBudget } from "@/features/budgets/new-budget";

export const metadata = { title: "Nuevo presupuesto" };

export default function Page() {
  return (
    <Suspense>
      <NewBudget />
    </Suspense>
  );
}
