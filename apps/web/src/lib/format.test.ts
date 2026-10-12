import { describe, expect, it } from "vitest";
import { formatOutput, formatUncertainty, formatValue } from "./format";

describe("format", () => {
  it("shows unknown for null values instead of zero", () => {
    expect(formatValue({ value: null, unit: "km / s" })).toBe("unknown");
  });

  it("keeps units", () => {
    expect(formatValue({ value: 768.0665, unit: "mas" })).toBe("768.067 mas");
  });

  it("renders each uncertainty type distinctly", () => {
    expect(formatUncertainty({ value: 1, uncertainty: { lower: 0.05, upper: 0.05, type: "symmetric_1sigma" } })).toContain("1σ");
    expect(formatUncertainty({ value: 1, uncertainty: { lower: 0.9, upper: 1.1, type: "interval_bounds_p16_p84" } })).toContain("16th–84th");
    expect(formatUncertainty({ value: 1, uncertainty: { lower: 0.1, upper: 0.2, type: "asymmetric_offsets" } })).toMatch(/^\+0\.2/);
    expect(formatUncertainty({ value: 1, uncertainty: null })).toBe("uncertainty not given");
  });

  it("formats model outputs of every kind", () => {
    expect(formatOutput({ value: 5.8723, unit: "yr" })).toBe("5.87230 yr");
    expect(formatOutput("not defined by this model")).toBe("not defined by this model");
    expect(formatOutput(undefined)).toBe("—");
  });
});
