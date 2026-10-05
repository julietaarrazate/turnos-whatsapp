import type { Metadata, Viewport } from "next";

import { Providers } from "@/components/providers";
import { RegisterServiceWorker } from "@/components/pwa/register-sw";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Plataforma para productoras", template: "%s · Plataforma" },
  description: "Presupuestos, propuestas, producción y rentabilidad para productoras de eventos.",
  appleWebApp: { capable: true, title: "Productoras", statusBarStyle: "default" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#3b4fd8",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es-AR">
      <body className="antialiased">
        <Providers>{children}</Providers>
        <RegisterServiceWorker />
      </body>
    </html>
  );
}
