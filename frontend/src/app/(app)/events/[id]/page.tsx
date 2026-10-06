import { EventSummary } from "@/features/events/event-detail";

export const metadata = { title: "Evento" };

export default async function Page({ params }: PageProps<"/events/[id]">) {
  const { id } = await params;
  return <EventSummary id={id} />;
}
