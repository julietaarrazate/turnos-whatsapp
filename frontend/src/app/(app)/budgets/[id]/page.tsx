import { BudgetEditor } from "@/features/budgets/budget-editor";

export const metadata = { title: "Presupuesto" };

export default async function Page({ params, searchParams }: PageProps<"/budgets/[id]">) {
  const { id } = await params;
  const query = await searchParams;
  // Después de "Duplicar": cuántos costos y markups cambiaron respecto del original.
  const copied =
    typeof query.costos === "string" && typeof query.reglas === "string"
      ? { costs: Number(query.costos) || 0, rules: Number(query.reglas) || 0 }
      : undefined;
  return <BudgetEditor budgetId={id} copied={copied} />;
}
