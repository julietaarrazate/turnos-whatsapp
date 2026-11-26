import { EventFiles } from "@/features/files/event-files";

export const metadata = { title: "Archivos del evento" };

export default async function Page({ params }: PageProps<"/events/[id]/files">) {
  const { id } = await params;
  return <EventFiles eventId={id} />;
}
