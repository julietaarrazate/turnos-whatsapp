"use client";

import Link from "next/link";

import { PageHeader } from "@/components/ui/page-header";
import { useSession } from "@/features/auth/session";
import { FollowUpCard } from "@/features/budgets/follow-up-card";
import { DashboardView } from "@/features/dashboard/dashboard";

function greeting(): string {
  const hour = Number(
    new Intl.DateTimeFormat("es-AR", { hour: "numeric", hourCycle: "h23", timeZone: "America/Argentina/Buenos_Aires" }).format(new Date()),
  );
  return hour < 13 ? "Buenos días" : hour < 20 ? "Buenas tardes" : "Buenas noches";
}

export default function DashboardPage() {
  const { me, can } = useSession();
  const firstName = me.user.name.split(" ")[0];
  return (
    <>
      <PageHeader title={`${greeting()}, ${firstName}`} description="Lo que pasa hoy en tu productora." />
      {can("dashboard.view") ? (
        <div className="flex flex-col gap-4">
          <DashboardView />
          <FollowUpCard />
        </div>
      ) : (
        <section className="rounded-xl border border-line bg-surface p-6 text-sm text-ink-muted">
          Tus eventos y tareas están en{" "}
          <Link href="/events" className="text-accent underline">
            Eventos
          </Link>
          .
        </section>
      )}
    </>
  );
}
