import { EventShell } from "@/features/events/event-detail";

export default async function Layout({ params, children }: LayoutProps<"/events/[id]">) {
  const { id } = await params;
  return <EventShell id={id}>{children}</EventShell>;
}
