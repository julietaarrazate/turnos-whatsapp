import { describe, expect, it } from "vitest";

import { SHARE_TEXT, whatsappShareUrl } from "./share-app";

describe("recomendar Handie", () => {
  it("arma el mensaje de WhatsApp con el texto y el link", () => {
    const url = whatsappShareUrl("https://handie.com.ar");
    expect(url.startsWith("https://wa.me/?text=")).toBe(true);
    expect(decodeURIComponent(url.split("text=")[1])).toBe(`${SHARE_TEXT}\nhttps://handie.com.ar`);
  });
});
