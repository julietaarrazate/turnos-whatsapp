"use client";

import { ProductDetail } from "@/features/catalog/product-detail";
import { useSegment } from "@/lib/route-params";

export function View() {
  return <ProductDetail id={useSegment(1)} />;
}
