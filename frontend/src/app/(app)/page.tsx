"use client";

import { PageHeader } from "@/components/ui/page-header";
import { useSession } from "@/features/auth/session";
import { FollowUpCard } from "@/features/budgets/follow-up-card";

function greeting(): string {
  const hour = Number(
    new Intl.DateTimeFormat("es-AR", { hour: "numeric", hourCycle: "h23", timeZone: "America/Argentina/Buenos_Aires" }).format(new Date()),
  );
  return hour < 13 ? "Buenos días" : hour < 20 ? "Buenas tardes" : "Buenas noches";
}

export default function DashboardPage() {
  const { me } = useSession();
  const firstName = me.user.name.split(" ")[0];
  return (
    <>
      <PageHeader title={`${greeting()}, ${firstName}`} description="Lo que pasa hoy en tu productora." />
      <div className="mb-4">
        <FollowUpCard />
      </div>
      <section className="rounded-xl border border-dashed border-line bg-surface p-6 text-sm text-ink-muted">
        El tablero (enviado, aceptado, en negociación y margen) llega en la Fase 5. Mientras tanto
        podés configurar tu organización e invitar a tu equipo desde <strong>Configuración</strong>.
      </section>
    </>
  );
}
