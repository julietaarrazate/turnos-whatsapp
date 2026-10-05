import { ClientDetail } from "@/features/clients/client-form";

export const metadata = { title: "Cliente" };

export default async function Page({ params }: PageProps<"/clients/[id]">) {
  const { id } = await params;
  return <ClientDetail id={id} />;
}
