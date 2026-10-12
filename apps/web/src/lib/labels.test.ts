import { describe, expect, it } from "vitest";
import { labelGroups } from "./labels";

// SYNTHETIC positions (pc) for testing label grouping only.
const bodies = [
  { id: 1, pos: [0, 0, 0] as const, label: "A" },
  { id: 2, pos: [1e-8, 0, 0] as const, label: "B" },
  { id: 3, pos: [1e-4, 0, 0] as const, label: "C" },
];

describe("labelGroups", () => {
  it("merges labels that would overlap at coarse zoom", () => {
    expect(labelGroups(bodies, 3e-4).map((g) => g.names)).toEqual([["A", "B"], ["C"]]);
  });

  it("separates them when zoomed in", () => {
    expect(labelGroups(bodies, 1e-7).map((g) => g.names)).toEqual([["A"], ["B"], ["C"]]);
  });
});
