import { describe, expect, it } from "vitest";

import { formatSize, shrinkImage, toBase64, uploadName } from "./files";

describe("toBase64", () => {
  it("codifica bytes binarios", async () => {
    const blob = new Blob([new Uint8Array([0xff, 0xd8, 0xff, 0x00, 0x41])]);
    expect(await toBase64(blob)).toBe("/9j/AEE=");
  });

  it("aguanta archivos más grandes que un bloque", async () => {
    const bytes = new Uint8Array(0x8000 * 2 + 3).fill(65);
    const decoded = atob(await toBase64(new Blob([bytes])));
    expect(decoded.length).toBe(bytes.length);
    expect(decoded.slice(0, 3)).toBe("AAA");
  });
});

describe("shrinkImage", () => {
  it("deja como están los PDF y las fotos chicas", async () => {
    const pdf = new File(["%PDF-1.7"], "oc.pdf", { type: "application/pdf" });
    expect(await shrinkImage(pdf)).toBe(pdf);
    const small = new File([new Uint8Array(1000)], "ticket.jpg", { type: "image/jpeg" });
    expect(await shrinkImage(small)).toBe(small);
  });

  it("si el navegador no puede achicarla, sube el original", async () => {
    // En node no hay createImageBitmap: cae al original sin romper.
    const big = new File([new Uint8Array(700 * 1024)], "foto.png", { type: "image/png" });
    expect(await shrinkImage(big)).toBe(big);
  });
});

describe("uploadName", () => {
  it("cambia la extensión cuando la foto se convirtió a JPEG", () => {
    const jpeg = new Blob([], { type: "image/jpeg" });
    expect(uploadName("ticket.png", jpeg)).toBe("ticket.jpg");
    expect(uploadName("ticket.JPEG", jpeg)).toBe("ticket.JPEG");
    expect(uploadName("factura.pdf", new Blob([], { type: "application/pdf" }))).toBe("factura.pdf");
  });
});

describe("formatSize", () => {
  it("muestra KB o MB con coma decimal", () => {
    expect(formatSize(320 * 1024)).toBe("320 KB");
    expect(formatSize(1.2 * 1024 * 1024 * 1024)).toBe("1,2 GB");
    expect(formatSize(100)).toBe("1 KB");
    expect(formatSize(1.5 * 1024 * 1024)).toBe("1,5 MB");
  });
});
