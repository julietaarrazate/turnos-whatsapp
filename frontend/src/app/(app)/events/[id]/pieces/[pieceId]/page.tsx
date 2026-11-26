import { PieceDetail } from "@/features/events/event-pieces";

export const metadata = { title: "Pieza" };

export default async function Page({ params }: PageProps<"/events/[id]/pieces/[pieceId]">) {
  const { id, pieceId } = await params;
  return <PieceDetail eventId={id} pieceId={pieceId} />;
}
