import type { Metadata } from "next";

import { PublicApprovalView } from "@/features/approvals/public-approval";
import { getPublicApproval } from "@/features/approvals/public-data";

export async function generateMetadata({ params }: PageProps<"/a/[token]">): Promise<Metadata> {
  const { token } = await params;
  const result = await getPublicApproval(token);
  if (result.kind !== "ok") return { title: "Aprobación de diseño", robots: { index: false, follow: false } };
  const { data } = result;
  const title = `${data.organization_name}: aprobá "${data.title}"`;
  return {
    title,
    robots: { index: false, follow: false },
    // En WhatsApp, la vista previa muestra el render mismo.
    openGraph: {
      title,
      description: `Diseño para ${data.event_name}. Tocá para aprobarlo o pedir cambios.`,
      type: "website",
      images: data.kind === "IMAGE" ? [`/api/v1/public/approvals/${encodeURIComponent(token)}/file`] : undefined,
    },
  };
}

export default async function Page({ params }: PageProps<"/a/[token]">) {
  const { token } = await params;
  const result = await getPublicApproval(token);
  if (result.kind !== "ok") {
    return (
      <main className="mx-auto flex min-h-dvh max-w-md flex-col justify-center gap-2 px-4 text-center">
        <h1 className="text-xl font-semibold">Link no encontrado</h1>
        <p className="text-sm text-ink-muted">Revisá que esté completo o pedile uno nuevo a la productora.</p>
      </main>
    );
  }
  return <PublicApprovalView data={result.data} token={token} />;
}
