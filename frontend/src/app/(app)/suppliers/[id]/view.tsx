"use client";

import { SupplierDetail } from "@/features/suppliers/supplier-form";
import { useSegment } from "@/lib/route-params";

export function View() {
  return <SupplierDetail id={useSegment(1)} />;
}
