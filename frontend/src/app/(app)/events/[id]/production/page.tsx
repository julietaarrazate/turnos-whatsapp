import { EventProduction } from "@/features/events/event-production";

export const metadata = { title: "Producción del evento" };

export default async function Page({ params }: PageProps<"/events/[id]/production">) {
  const { id } = await params;
  return <EventProduction id={id} />;
}
