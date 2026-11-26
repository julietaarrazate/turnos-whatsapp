import type { Metadata, Viewport } from "next";
import { Inter_Tight } from "next/font/google";
import { connection } from "next/server";

import { Providers } from "@/components/providers";
import { RegisterServiceWorker } from "@/components/pwa/register-sw";

import "./globals.css";

// Self-hosted por Next en el build: no se pide nada a Google desde el navegador (CSP font-src 'self').
const interTight = Inter_Tight({ subsets: ["latin"], variable: "--font-inter-tight", display: "swap" });

export const metadata: Metadata = {
  title: { default: "Handie", template: "%s · Handie" },
  applicationName: "Handie",
  description: "Presupuestos, producción y montaje de tus eventos, en un solo lugar.",
  appleWebApp: { capable: true, title: "Handie", statusBarStyle: "default" },
  // La miniatura al compartir por WhatsApp sale de opengraph-image.png (Next arma la URL completa
  // con el dominio de producción de Vercel).
  openGraph: {
    type: "website",
    siteName: "Handie",
    title: "Handie",
    description: "Presupuestos, producción y montaje de tus eventos, en un solo lugar.",
    locale: "es_AR",
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // Se usa como app instalada: sin zoom con dos dedos ni al tocar un campo.
  maximumScale: 1,
  userScalable: false,
  viewportFit: "cover",
  // La barra del teléfono acompaña al modo claro u oscuro.
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#2b2fa8" },
    { media: "(prefers-color-scheme: dark)", color: "#1f2250" },
  ],
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
