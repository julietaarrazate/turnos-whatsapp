import { BudgetEditor } from "@/features/budgets/budget-editor";

export const metadata = { title: "Presupuesto" };

export default async function Page({ params }: PageProps<"/budgets/[id]">) {
  const { id } = await params;
  return <BudgetEditor budgetId={id} />;
}
