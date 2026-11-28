import { STATIC_ID } from "@/lib/static-id";

import { View } from "./view";

export const metadata = { title: "Cliente" };

// Plantilla armada de antemano: el ID real lo lee la pantalla de la dirección (ver next.config).
export const dynamicParams = false;
export function generateStaticParams() {
  return [{ id: STATIC_ID }];
}

export default function Page() {
  return <View />;
}
