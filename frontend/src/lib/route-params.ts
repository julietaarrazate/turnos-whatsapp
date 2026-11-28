"use client";

import { usePathname } from "next/navigation";

/**
 * Las pantallas con ID (un evento, un presupuesto…) se arman una sola vez, de antemano, como
 * plantilla (`/events/_`): así abren al instante y sin pedirle nada al servidor de Vercel. El
 * ID real sale de la dirección del navegador ("/events/123/pieces" → "123").
 */
export function segmentAt(pathname: string, index: number): string {
  return decodeURIComponent(pathname.split("/").filter(Boolean)[index] ?? "");
}

export function useSegment(index: number): string {
  return segmentAt(usePathname() ?? "", index);
}
