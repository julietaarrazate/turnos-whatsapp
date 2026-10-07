import { PageHeader } from "@/components/ui/page-header";
import { ProfitabilityReport } from "@/features/dashboard/reports";

export const metadata = { title: "Reportes" };

export default function Page() {
  return (
    <>
      <PageHeader title="Rentabilidad" description="Estimada vs real, por evento, cliente o mes." />
      <ProfitabilityReport />
    </>
  );
}
