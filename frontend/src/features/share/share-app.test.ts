import { describe, expect, it } from "vitest";

import { isPreviewBot } from "@/proxy";

import { SHARE_TEXT, shareUrl, whatsappShareUrl } from "./share-app";

describe("recomendar Handie", () => {
  it("arma el mensaje de WhatsApp con el texto y el link", () => {
    const url = whatsappShareUrl("https://handie.com.ar");
    expect(url.startsWith("https://wa.me/?text=")).toBe(true);
    expect(decodeURIComponent(url.split("text=")[1])).toBe(`${SHARE_TEXT}\nhttps://handie.com.ar`);
  });

  it("comparte la página de ingreso directa, sin redirección", () => {
    expect(shareUrl("https://handie.com.ar")).toBe("https://handie.com.ar/login?ref=compartir");
  });

  it("reconoce al lector de vistas previas de WhatsApp y no a un navegador", () => {
    expect(isPreviewBot("WhatsApp/2.23.20.0 A")).toBe(true);
    expect(isPreviewBot("facebookexternalhit/1.1")).toBe(true);
    expect(isPreviewBot("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0) Mobile Safari")).toBe(false);
    expect(isPreviewBot(null)).toBe(false);
  });
});
