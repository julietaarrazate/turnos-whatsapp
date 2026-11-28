import { STATIC_ID } from "@/lib/static-id";

import { LayoutView } from "./layout-view";

export const dynamicParams = false;
export function generateStaticParams() {
  return [{ id: STATIC_ID }];
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return <LayoutView>{children}</LayoutView>;
}
