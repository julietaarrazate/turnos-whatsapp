import { EventBudgets } from "@/features/events/event-detail";

export const metadata = { title: "Presupuestos del evento" };

export default async function Page({ params }: PageProps<"/events/[id]/budgets">) {
  const { id } = await params;
  return <EventBudgets id={id} />;
}
