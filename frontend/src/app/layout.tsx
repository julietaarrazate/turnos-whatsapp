import type { Metadata, Viewport } from "next";
import { Inter_Tight } from "next/font/google";
import { connection } from "next/server";

import { Providers } from "@/components/providers";
import { RegisterServiceWorker } from "@/components/pwa/register-sw";

import "./globals.css";

// Self-hosted por Next en el build: no se pide nada a Google desde el navegador (CSP font-src 'self').
const interTight = Inter_Tight({ subsets: ["latin"], variable: "--font-inter-tight", display: "swap" });

export const metadata: Metadata = {
  title: { default: "Plataforma para productoras", template: "%s · Plataforma" },
  description: "Presupuestos, propuestas, producción y rentabilidad para productoras de eventos.",
  appleWebApp: { capable: true, title: "Productoras", statusBarStyle: "default" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#2b2fa8",
};

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  // Render por request: el nonce de la CSP (src/proxy.ts) solo existe en el request, y Next se lo
  // pone a sus scripts al renderizar. Una página estática no lo tendría y la CSP la bloquearía.
  await connection();
  return (
    <html lang="es-AR" className={interTight.variable}>
      <body className="antialiased">
        <Providers>{children}</Providers>
        <RegisterServiceWorker />
      </body>
    </html>
  );
}
