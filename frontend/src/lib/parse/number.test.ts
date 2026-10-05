import { describe, expect, it } from "vitest";

import { parseDecimalAR } from "./number";

describe("parseDecimalAR", () => {
  it.each([
    ["0", "0"],
    ["15", "15"],
    ["1,5", "1.5"],
    ["1,50", "1.5"],
    ["0,25", "0.25"],
    [",5", "0.5"],
    ["1.500", "1500"],
    ["1.500,75", "1500.75"],
    ["1.234.567", "1234567"],
    ["1.234.567,89", "1234567.89"],
    ["100.000", "100000"],
    ["1.5", "1.5"],
    ["12.75", "12.75"],
    ["6.5", "6.5"],
    ["1.2345", "1.2345"],
    ["0.500", "0.5"],
    ["1,234.5", "1234.5"],
    ["1,234,567", "1234567"],
    ["$ 100.000", "100000"],
    ["  42  ", "42"],
    ["007", "7"],
  ])("'%s' → %s", (input, expected) => {
    expect(parseDecimalAR(input)).toBe(expected);
  });

  it.each(["", "abc", "1,2,3", "1.23.4", "1..5", "1,5,", "12a", "-", ".", ",", "1.000,5.3"])(
    "rechaza '%s'",
    (input) => {
      expect(parseDecimalAR(input)).toBeNull();
    },
  );

  it("solo acepta negativos si se pide", () => {
    expect(parseDecimalAR("-1,5")).toBeNull();
    expect(parseDecimalAR("-1,5", { allowNegative: true })).toBe("-1.5");
    expect(parseDecimalAR("-0", { allowNegative: true })).toBe("0");
  });
});
