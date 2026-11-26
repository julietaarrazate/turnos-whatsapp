import { EventPieces } from "@/features/events/event-pieces";

export const metadata = { title: "Piezas del evento" };

export default async function Page({ params }: PageProps<"/events/[id]/pieces">) {
  const { id } = await params;
  return <EventPieces id={id} />;
}
