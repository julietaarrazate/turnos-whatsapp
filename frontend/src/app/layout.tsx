import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Plataforma para productoras",
  description: "Presupuestos, propuestas, producción y rentabilidad para productoras de eventos.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#111827",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es-AR">
      <body className="bg-white text-neutral-900 antialiased">{children}</body>
    </html>
  );
}
