import { describe, expect, it } from "vitest";
import { cellOf, neighbourhood, rebase } from "./space";

describe("floating origin", () => {
  it("keeps sub-AU precision far from the barycentre after rebasing", () => {
    // Two points 1e-6 pc apart, 100 pc from the origin. Converting absolute positions to
    // float32 would lose the separation; rebasing first keeps it.
    const far = 100;
    const pts = [
      [far, 0, 0],
      [far + 1e-6, 0, 0],
    ] as const;
    const naive = new Float32Array([pts[0][0], pts[1][0]]);
    expect((naive[1] ?? NaN) - (naive[0] ?? NaN)).not.toBeCloseTo(1e-6, 9);
    const rebased = rebase(pts, [far, 0, 0]);
    expect((rebased[3] ?? NaN) - (rebased[0] ?? NaN)).toBeCloseTo(1e-6, 9);
  });
});

describe("octree", () => {
  it("finds the containing cell and rejects points outside the root", () => {
    expect(cellOf([0, 0, 0], 1)).toEqual([1, 1, 1]);
    expect(cellOf([-1, -1, -1], 1)).toEqual([0, 0, 0]);
    expect(cellOf([500, 0, 0], 1)).toBeNull();
  });

  it("lists in-range neighbours", () => {
    expect(neighbourhood([0, 0, 0], 2)).toHaveLength(8);
    expect(neighbourhood([1, 1, 1], 2)).toHaveLength(27);
  });
});

describe("floating-origin validation (CLAUDE.md §7: Earth, Proxima, Sgr A*)", () => {
  // Focus distances from the barycentre at three scales, and separations down to about
  // Earth-Moon scale (1e-8 pc). "No visible jitter": when a separation fills a 1000-px
  // viewport, its error must stay below one pixel, i.e. below 1e-3 of the separation.
  // (Absolute float64 itself resolves ~1.8e-12 pc at 8122 pc, so 1e-8 pc separations there
  // carry ~2e-4 relative error before any float32 conversion: sub-pixel, but not 1e-6.)
  const foci: Record<string, number> = { earth: 4.8e-6, proxima: 1.3, sgrA: 8122 };
  const separations = [1e-8, 1e-6, 1e-3, 1];

  for (const [name, r] of Object.entries(foci)) {
    it(`keeps separations when focused at ${name} (${r} pc)`, () => {
      const focus = [r, r / 3, -r / 7] as const;
      for (const sep of separations) {
        const p = [focus[0] + sep, focus[1] - sep / 2, focus[2] + sep / 3] as const;
        const f32 = rebase([p], focus);
        const exact = [sep, -sep / 2, sep / 3];
        exact.forEach((e, i) => {
          expect(Math.abs((f32[i] ?? NaN) - e) / Math.abs(e)).toBeLessThan(1e-3);
        });
      }
    });
  }

  it("shows why rebasing is needed: absolute float32 at Sgr A* distance loses AU scales", () => {
    const r = 8122;
    const sep = 1e-6; // about 0.2 AU
    const a = new Float32Array([r, r + sep]);
    expect(Math.abs((a[1] ?? NaN) - (a[0] ?? NaN) - sep) / sep).toBeGreaterThan(0.1);
  });
});
