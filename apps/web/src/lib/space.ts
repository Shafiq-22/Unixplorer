// Floating origin and octree addressing for the 3D view (CLAUDE.md §7, §12).
// Positions stay float64 (JS number) on the CPU; only camera-relative offsets become float32.

export type Vec3 = readonly [number, number, number];

/** Must match services/api/atlas_api/routers/stars.py */
export const ROOT_HALF_PC = 128;

/** Positions relative to `origin`, as float32 for a GPU buffer. */
export function rebase(positions: readonly Vec3[], origin: Vec3): Float32Array {
  const out = new Float32Array(positions.length * 3);
  positions.forEach((p, i) => {
    out[i * 3] = p[0] - origin[0];
    out[i * 3 + 1] = p[1] - origin[1];
    out[i * 3 + 2] = p[2] - origin[2];
  });
  return out;
}

/** Octree cell index containing a point at `level`, or null outside the root cube. */
export function cellOf(p: Vec3, level: number): Vec3 | null {
  const n = 2 ** level;
  const size = (2 * ROOT_HALF_PC) / n;
  const idx = p.map((v) => Math.floor((v + ROOT_HALF_PC) / size)) as unknown as Vec3;
  return idx.every((i) => i >= 0 && i < n) ? idx : null;
}

/** The cell and its in-range neighbours (up to 27 cells). */
export function neighbourhood(cell: Vec3, level: number): Vec3[] {
  const n = 2 ** level;
  const out: Vec3[] = [];
  for (let dx = -1; dx <= 1; dx++)
    for (let dy = -1; dy <= 1; dy++)
      for (let dz = -1; dz <= 1; dz++) {
        const c: Vec3 = [cell[0] + dx, cell[1] + dy, cell[2] + dz];
        if (c.every((i) => i >= 0 && i < n)) out.push(c);
      }
  return out;
}

export function lerp3(a: Vec3, b: Vec3, w: number): Vec3 {
  return [a[0] + (b[0] - a[0]) * w, a[1] + (b[1] - a[1]) * w, a[2] + (b[2] - a[2]) * w];
}
