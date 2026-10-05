import { PageHeader } from "@/components/ui/page-header";

export function ComingSoon({ title, phase, description }: { title: string; phase: number; description: string }) {
  return (
    <>
      <PageHeader title={title} />
      <section className="rounded-xl border border-dashed border-line bg-surface p-6">
        <p className="text-sm font-medium text-ink">En construcción · Fase {phase}</p>
        <p className="mt-1 text-sm text-ink-muted">{description}</p>
      </section>
    </>
  );
}
