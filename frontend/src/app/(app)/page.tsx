"use client";

import Link from "next/link";

import { PageHeader } from "@/components/ui/page-header";
import { useSession } from "@/features/auth/session";
import { FollowUpCard } from "@/features/budgets/follow-up-card";
import { DashboardView } from "@/features/dashboard/dashboard";
import { MyWork } from "@/features/my-work/my-work";

function greeting(): string {
  const hour = Number(
    new Intl.DateTimeFormat("es-AR", { hour: "numeric", hourCycle: "h23", timeZone: "America/Argentina/Buenos_Aires" }).format(new Date()),
  );
  return hour < 13 ? "Buenos días" : hour < 20 ? "Buenas tardes" : "Buenas noches";
}

export default function DashboardPage() {
  const { me, can } = useSession();
  const firstName = me.user.name.split(" ")[0];
  const title = `${greeting()}, ${firstName}`;
  // Taller/montaje: su inicio es lo que tiene asignado.
  if (!can("org.view")) return <MyWork />;
  if (can("dashboard.view")) {
    return (
      <div className="flex flex-col gap-5">
        <DashboardView greeting={title} />
        <FollowUpCard />
      </div>
    );
  }
  return (
    <>
      <PageHeader title={title} description="Lo que pasa hoy en tu productora." />
      <section className="rounded-xl border border-line bg-surface p-6 text-sm text-ink-muted">
        Lo que tenés asignado está en{" "}
        <Link href="/my-work" className="text-accent underline">
          Mis tareas
        </Link>
        , y los eventos en{" "}
        <Link href="/events" className="text-accent underline">
          Eventos
        </Link>
        .
      </section>
    </>
  );
}
