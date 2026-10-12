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
