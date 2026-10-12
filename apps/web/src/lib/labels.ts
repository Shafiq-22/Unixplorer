import type { Vec3 } from "./space";

export interface LabelledPoint {
  readonly pos: Vec3;
  readonly label: string;
}

/** Group bodies whose markers would overlap on screen (closer than 3% of the camera
 * distance) under one label, e.g. "Earth, Moon" at planetary scale. */
export function labelGroups(bodies: readonly LabelledPoint[], viewPc: number): { pos: Vec3; names: string[] }[] {
  const groups: { pos: Vec3; names: string[] }[] = [];
  for (const b of bodies) {
    const g = groups.find((x) => Math.hypot(x.pos[0] - b.pos[0], x.pos[1] - b.pos[1], x.pos[2] - b.pos[2]) < viewPc * 0.03);
    if (g) g.names.push(b.label);
    else groups.push({ pos: b.pos, names: [b.label] });
  }
  return groups;
}

