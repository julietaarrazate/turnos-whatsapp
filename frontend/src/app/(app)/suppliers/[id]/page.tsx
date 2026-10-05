import { SupplierDetail } from "@/features/suppliers/supplier-form";

export const metadata = { title: "Proveedor" };

export default async function Page({ params }: PageProps<"/suppliers/[id]">) {
  const { id } = await params;
  return <SupplierDetail id={id} />;
}
