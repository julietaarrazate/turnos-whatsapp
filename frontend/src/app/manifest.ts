import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Handie",
    short_name: "Handie",
    description: "Presupuestos, producción y montaje de tus eventos, en un solo lugar.",
    start_url: "/",
    display: "standalone",
    background_color: "#f6f7f9",
    theme_color: "#2b2fa8",
    lang: "es-AR",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
      { src: "/icons/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
