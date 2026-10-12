import type { Measurement, QuantityValue } from "@atlas/shared-types";

// Display helpers. They format numbers the API returned; they never compute physics.

export function fmt(x: number, digits = 6): string {
  if (x === 0) return "0";
  const abs = Math.abs(x);
  return abs >= 1e6 || abs < 1e-3 ? x.toExponential(digits - 1) : x.toPrecision(digits);
}

export function formatUncertainty(m: Pick<Measurement, "value" | "uncertainty">): string {
  const u = m.uncertainty;
  if (m.value === null) return "";
  if (!u) return "uncertainty not given";
  switch (u.type) {
    case "symmetric_1sigma":
      return u.lower === null ? "" : `± ${fmt(u.lower, 3)} (1σ)`;
    case "asymmetric_offsets":
      return `+${u.upper === null ? "?" : fmt(u.upper, 3)} / −${u.lower === null ? "?" : fmt(u.lower, 3)}`;
    case "interval_bounds_p16_p84":
      return `[${u.lower === null ? "?" : fmt(u.lower, 6)} – ${u.upper === null ? "?" : fmt(u.upper, 6)}] (16th–84th pct)`;
    case "upper_limit":
      return "upper limit";
    case "lower_limit":
      return "lower limit";
    default:
      return u.type;
  }
}

export function formatValue(m: Pick<Measurement, "value" | "unit">): string {
  return m.value === null ? "unknown" : `${fmt(m.value)}${m.unit ? ` ${m.unit}` : ""}`;
}

export function isQuantity(v: unknown): v is QuantityValue {
  return typeof v === "object" && v !== null && "value" in v && "unit" in v;
}

export function formatOutput(v: QuantityValue | number | string | undefined): string {
  if (v === undefined) return "—";
  if (typeof v === "string") return v;
  if (typeof v === "number") return fmt(v);
  return `${fmt(v.value)} ${v.unit}`;
}

export const STATE_LABEL: Record<string, string> = {
  measured: "measured",
  published_estimate: "published estimate",
  derived: "derived",
  model_predicted: "model predicted",
  inferred: "inferred",
  illustrative: "illustrative",
  unknown: "unknown",
  conflicting: "conflicting",
  invalid: "invalid",
  below_detection: "below detection",
  not_applicable: "not applicable",
};
