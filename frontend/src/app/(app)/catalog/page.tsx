import { ComingSoon } from "@/components/coming-soon";

export const metadata = { title: "Catálogo" };

export default function Page() {
  return <ComingSoon title="Catálogo" phase={2} description="Productos, proveedores, historial de costos, importación desde Excel y aumentos masivos." />;
}
