import { EventProfitability } from "@/features/events/event-profitability";

export const metadata = { title: "Rentabilidad del evento" };

export default async function Page({ params }: PageProps<"/events/[id]/profitability">) {
  const { id } = await params;
  return <EventProfitability id={id} />;
}
