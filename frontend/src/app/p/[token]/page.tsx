import type { Metadata } from "next";

import { PublicProposalView } from "@/features/proposals/public-proposal";
import { getPublicProposal } from "@/features/proposals/public-data";

export async function generateMetadata({ params }: PageProps<"/p/[token]">): Promise<Metadata> {
  const { token } = await params;
  const result = await getPublicProposal(token);
  // Vista previa de WhatsApp: título y productora, nunca montos (ARCHITECTURE §5.3).
  const title =
    result.kind === "ok"
      ? `Propuesta de ${result.data.proposal.organization.name}: ${result.data.proposal.title}`
      : "Propuesta";
  return {
    title,
    robots: { index: false, follow: false },
    openGraph: { title, description: "Propuesta comercial", type: "website" },
  };
}

export default async function Page({ params }: PageProps<"/p/[token]">) {
  const { token } = await params;
  const result = await getPublicProposal(token);
  if (result.kind !== "ok") {
    return (
      <main className="mx-auto flex min-h-dvh max-w-md flex-col justify-center gap-2 px-4 text-center">
        <h1 className="text-xl font-semibold">{result.kind === "revoked" ? "Propuesta anulada" : "Propuesta no encontrada"}</h1>
        <p className="text-sm text-ink-muted">
          {result.kind === "revoked"
            ? "La productora anuló esta propuesta. Pedile una nueva."
            : "El link no es válido. Revisá que esté completo o pedile uno nuevo a la productora."}
        </p>
      </main>
    );
  }
  return <PublicProposalView data={result.data} token={token} />;
}
