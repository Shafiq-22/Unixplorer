import type { TrajectorySample } from "@atlas/shared-types";

// Frame-rate-independent traversal clock (CLAUDE.md §10). The only state is the simulated
// coordinate time; every displayed quantity is a pure function of it, interpolated between
// samples the backend computed (CLAUDE.md §4: no physics formulas in the UI).

export type ClockStatus = "running" | "paused" | "cancelled" | "arrived";

export interface ClockState {
  readonly simTimeYr: number;
  readonly status: ClockStatus;
}

export interface TraversalView {
  readonly coordinateTimeYr: number;
  readonly properTimeYr: number | null;
  readonly fraction: number;
  readonly speedC: number;
}

/** Advance by a wall-clock tick. `yearsPerSecond` is the user's time compression. */
export function advance(
  state: ClockState,
  tickMs: number,
  yearsPerSecond: number,
  totalYr: number,
): ClockState {
  if (state.status !== "running") return state;
  const next = state.simTimeYr + (tickMs / 1000) * yearsPerSecond;
  return next >= totalYr
    ? { simTimeYr: totalYr, status: "arrived" }
    : { simTimeYr: next, status: "running" };
}

function lerp(a: number, b: number, w: number): number {
  return a + (b - a) * w;
}

/** State at a coordinate time, by linear interpolation between backend samples. */
export function viewAt(samples: readonly TrajectorySample[], tYr: number): TraversalView {
  const first = samples[0];
  const last = samples[samples.length - 1];
  if (!first || !last) throw new Error("trajectory has no samples");
  if (tYr <= first.coordinate_time_yr) return toView(first);
  if (tYr >= last.coordinate_time_yr) return toView(last);
  let lo = 0;
  let hi = samples.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    const s = samples[mid];
    if (s && s.coordinate_time_yr <= tYr) lo = mid;
    else hi = mid;
  }
  const a = samples[lo];
  const b = samples[hi];
  if (!a || !b) throw new Error("interpolation index out of range");
  const w = (tYr - a.coordinate_time_yr) / (b.coordinate_time_yr - a.coordinate_time_yr);
  return {
    coordinateTimeYr: tYr,
    properTimeYr:
      a.proper_time_yr === null || b.proper_time_yr === null
        ? null
        : lerp(a.proper_time_yr, b.proper_time_yr, w),
    fraction: lerp(a.fraction, b.fraction, w),
    speedC: lerp(a.speed_c, b.speed_c, w),
  };
}

function toView(s: TrajectorySample): TraversalView {
  return {
    coordinateTimeYr: s.coordinate_time_yr,
    properTimeYr: s.proper_time_yr,
    fraction: s.fraction,
    speedC: s.speed_c,
  };
}
