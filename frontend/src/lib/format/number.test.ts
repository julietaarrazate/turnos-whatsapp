import { describe, expect, it } from "vitest";

import { formatDecimal, formatMoney, formatPercent, formatQuantity } from "./number";

describe("formatMoney", () => {
  it.each([
    ["270000.00", "$ 270.000,00"],
    ["1137400", "$ 1.137.400,00"],
    ["0.5", "$ 0,50"],
    ["133333.33", "$ 133.333,33"],
    ["-20000", "-$ 20.000,00"],
    ["999.995", "$ 1.000,00"],
    ["12345678901234567890.12", "$ 12.345.678.901.234.567.890,12"],
  ])("%s → %s", (input, expected) => {
    expect(formatMoney(input)).toBe(expected);
  });

  it("USD", () => {
    expect(formatMoney("800", "USD")).toBe("US$ 800,00");
  });
});

describe("formatPercent", () => {
  it.each([
    ["0.230769", "23,1 %"],
    ["0.35", "35,0 %"],
    ["0.2553", "25,5 %"],
    ["1", "100,0 %"],
    ["0", "0,0 %"],
    ["-0.052", "-5,2 %"],
    ["0.25934", "25,9 %"],
  ])("%s → %s", (input, expected) => {
    expect(formatPercent(input)).toBe(expected);
  });

  it("con 2 decimales", () => {
    expect(formatPercent("0.230769", 2)).toBe("23,08 %");
  });
});

describe("formatDecimal", () => {
  it("rechaza lo que no es un decimal", () => {
    expect(() => formatDecimal("1e5")).toThrow();
    expect(() => formatDecimal("abc")).toThrow();
  });

  it("no muestra -0", () => {
    expect(formatDecimal("-0.001")).toBe("0,00");
  });
});

describe("formatQuantity", () => {
  it("muestra solo los decimales significativos", () => {
    expect(formatQuantity("1.5000")).toBe("1,5");
    expect(formatQuantity("2.0000")).toBe("2");
    expect(formatQuantity("1500")).toBe("1.500");
    expect(formatQuantity("0.25")).toBe("0,25");
  });
});
