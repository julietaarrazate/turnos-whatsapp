import { describe, expect, it } from "vitest";

import { formatSeconds, pickMimeType, voiceFilename } from "./voice-recorder";

describe("notas de voz", () => {
  it("elige el formato que el navegador sabe grabar", () => {
    expect(pickMimeType((t) => t.startsWith("audio/webm"))).toBe("audio/webm;codecs=opus");
    expect(pickMimeType((t) => t === "audio/mp4")).toBe("audio/mp4"); // iPhone
    expect(pickMimeType(() => false)).toBeUndefined();
  });

  it("nombra el archivo según el formato", () => {
    expect(voiceFilename("audio/webm;codecs=opus")).toBe("nota.webm");
    expect(voiceFilename("audio/mp4")).toBe("nota.m4a");
    expect(voiceFilename("audio/ogg;codecs=opus")).toBe("nota.ogg");
  });

  it("muestra el tiempo como 0:07", () => {
    expect(formatSeconds(7.8)).toBe("0:07");
    expect(formatSeconds(60)).toBe("1:00");
  });
});
