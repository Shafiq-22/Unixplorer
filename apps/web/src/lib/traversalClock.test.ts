import { describe, expect, it } from "vitest";
import type { TrajectorySample } from "@atlas/shared-types";
import { advance, viewAt, type ClockState } from "./traversalClock";

// SYNTHETIC samples for testing interpolation only (not physics output).
const samples: TrajectorySample[] = [
  { coordinate_time_yr: 0, proper_time_yr: 0, fraction: 0, speed_c: 0 },
  { coordinate_time_yr: 1, proper_time_yr: 0.8, fraction: 0.25, speed_c: 0.6 },
  { coordinate_time_yr: 2, proper_time_yr: 1.6, fraction: 0.75, speed_c: 0.6 },
  { coordinate_time_yr: 3, proper_time_yr: 2.0, fraction: 1, speed_c: 0 },
];

function run(tickMs: number, wallMs: number, rate: number, total: number): ClockState {
  let s: ClockState = { simTimeYr: 0, status: "running" };
  for (let t = 0; t < wallMs; t += tickMs) s = advance(s, tickMs, rate, total);
  return s;
}

describe("traversal clock", () => {
  it("is frame-rate independent: 16 ms and 100 ms ticks give the same state", () => {
    const wall = 2_400; // divisible by both 16 and 100
    const a = run(16, wall, 0.5, 3);
    const b = run(100, wall, 0.5, 3);
    expect(a.simTimeYr).toBeCloseTo(b.simTimeYr, 12);
    expect(viewAt(samples, a.simTimeYr).fraction).toBeCloseTo(viewAt(samples, b.simTimeYr).fraction, 12);
  });

  it("does not advance while paused or cancelled", () => {
    for (const status of ["paused", "cancelled", "arrived"] as const) {
      const s: ClockState = { simTimeYr: 1.5, status };
      expect(advance(s, 1000, 10, 3)).toBe(s);
    }
  });

  it("stops exactly at arrival", () => {
    const s = advance({ simTimeYr: 2.9, status: "running" }, 1000, 1, 3);
    expect(s).toEqual({ simTimeYr: 3, status: "arrived" });
  });
});

describe("viewAt", () => {
  it("interpolates between backend samples", () => {
    const v = viewAt(samples, 1.5);
    expect(v.fraction).toBeCloseTo(0.5, 12);
    expect(v.properTimeYr).toBeCloseTo(1.2, 12);
  });

  it("keeps proper time null when the model does not define it", () => {
    const nullTau = samples.map((s) => ({ ...s, proper_time_yr: null }));
    expect(viewAt(nullTau, 1.5).properTimeYr).toBeNull();
  });

  it("clamps to the ends of the trajectory", () => {
    expect(viewAt(samples, -1).fraction).toBe(0);
    expect(viewAt(samples, 99).fraction).toBe(1);
  });
});
