import { describe, expect, it } from "vitest";
import { AU_PER_PC, formatDistance, formatDuration, formatOutput, formatTimeOutput, formatUncertainty, formatValue } from "./format";

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

describe("unit choice", () => {
  it("uses the exact pc-AU definition", () => {
    expect(AU_PER_PC).toBeCloseTo(206264.80624709636, 6);
  });

  it("shows planetary distances in AU and stellar ones in pc", () => {
    expect(formatDistance(2.5e-6, 0.515662)).toBe("0.515662 AU");
    expect(formatDistance(1.30191, 268536)).toBe("1.30191 pc");
  });

  it("shows short durations in days, hours or seconds", () => {
    expect(formatDuration(5.87)).toBe("5.87000 yr");
    expect(formatDuration(0.5)).toBe("182.625 d");
    expect(formatDuration(1 / 365.25 / 24 * 3)).toBe("3.00000 h");
    expect(formatDuration(1 / 365.25 / 86_400 * 500)).toBe("500.000 s");
    expect(formatTimeOutput({ value: 0.5, unit: "yr" })).toBe("182.625 d");
    expect(formatTimeOutput("not defined by this model")).toBe("not defined by this model");
  });
});
