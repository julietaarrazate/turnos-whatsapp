import { describe, expect, it } from "vitest";

import { fractionToPercentInput, percentToFraction } from "./percent";

describe("percentToFraction", () => {
  it.each([
    ["30", "0.3"],
    ["3,5", "0.035"],
    ["12,75 %", "0.1275"],
    ["0", "0"],
    ["100", "1"],
    ["250", "2.5"],
    ["0,5", "0.005"],
    ["1.000", "10"],
  ])("%s → %s", (input, expected) => {
    expect(percentToFraction(input)).toBe(expected);
  });

  it("rechaza lo que no es un número", () => {
    expect(percentToFraction("abc")).toBeNull();
    expect(percentToFraction("")).toBeNull();
  });
});

describe("fractionToPercentInput", () => {
  it.each([
    ["0.300000", "30"],
    ["0.035000", "3,5"],
    ["0.1275", "12,75"],
    ["0", "0"],
    ["1", "100"],
    ["2.5", "250"],
    ["0.005", "0,5"],
  ])("%s → %s", (input, expected) => {
    expect(fractionToPercentInput(input)).toBe(expected);
  });
});
