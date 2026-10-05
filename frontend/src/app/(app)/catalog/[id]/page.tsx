import { ProductDetail } from "@/features/catalog/product-detail";

export const metadata = { title: "Producto" };

export default async function Page({ params }: PageProps<"/catalog/[id]">) {
  const { id } = await params;
  return <ProductDetail id={id} />;
}
