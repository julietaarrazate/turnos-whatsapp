import { EventExpenses } from "@/features/events/event-expenses";

export const metadata = { title: "Gastos del evento" };

export default async function Page({ params }: PageProps<"/events/[id]/expenses">) {
  const { id } = await params;
  return <EventExpenses id={id} />;
}
