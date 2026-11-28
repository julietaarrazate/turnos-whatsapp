import { describe, expect, it } from "vitest";

import { describeDevice, timeAgo } from "./device";

describe("describeDevice", () => {
  it.each([
    [
      "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1",
      "iPhone · Safari",
    ],
    [
      "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
      "Android · Chrome",
    ],
    [
      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
      "Mac · Chrome",
    ],
    [
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
      "Windows · Edge",
    ],
    [null, "Dispositivo desconocido"],
    ["curl/8.0", "Dispositivo desconocido"],
  ])("%s", (ua, expected) => {
    expect(describeDevice(ua)).toBe(expected);
  });
});

describe("timeAgo", () => {
  const now = new Date("2026-11-28T12:00:00Z");
  it.each([
    [null, "nunca"],
    ["2026-11-28T11:59:40Z", "recién"],
    ["2026-11-28T11:55:00Z", "hace 5 min"],
    ["2026-11-28T09:00:00Z", "hace 3 h"],
    ["2026-11-27T12:00:00Z", "hace 1 día"],
    ["2026-11-20T12:00:00Z", "hace 8 días"],
  ])("%s", (iso, expected) => {
    expect(timeAgo(iso, now)).toBe(expected);
  });
});
