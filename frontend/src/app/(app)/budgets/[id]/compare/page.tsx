import { CompareVersions } from "@/features/budgets/compare-versions";

export const metadata = { title: "Comparar versiones" };

export default async function Page({ params, searchParams }: PageProps<"/budgets/[id]/compare">) {
  const { id } = await params;
  const query = await searchParams;
  const from = Number(query.from) || 1;
  const to = Number(query.to) || from + 1;
  return <CompareVersions budgetId={id} from={from} to={to} />;
}
