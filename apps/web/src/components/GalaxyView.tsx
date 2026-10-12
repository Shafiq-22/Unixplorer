"use client";

import type React from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useThree } from "@react-three/fiber";
import { Html, Line, OrbitControls } from "@react-three/drei";
import { api } from "@/lib/api";
import { labelGroups } from "@/lib/labels";
import { cellOf, neighbourhood, rebase, type Vec3 } from "@/lib/space";

export interface Marker {
  readonly pos: Vec3;
  readonly label: string;
}

export interface BodyMarker {
  readonly id: number;
  readonly pos: Vec3;
  readonly label: string;
}

/** Closest and farthest camera distances (pc): Earth-Moon scale to beyond the snapshot. */
export const MIN_VIEW_PC = 2e-9;
export const MAX_VIEW_PC = 2000;

interface Props {
  focus: Vec3;
  zoom: { distancePc: number; nonce: number };
  onViewDistance: (pc: number) => void;
  bodies: readonly BodyMarker[];
  selected: Marker | null;
  route: { a: Vec3; b: Vec3 } | null;
  ship: Vec3 | null;
  reducedMotion: boolean;
}

interface Star {
  p: Vec3;
  g: number | null;
}

const DETAIL_LEVEL = 2; // 64 pc cells
const TILE_LIMIT = 3000;

/** Loads the level-0 root tile plus finer tiles around the focus; never the whole catalogue. */
function useStars(focus: Vec3): Map<number, Star> {
  const [stars, setStars] = useState<Map<number, Star>>(new Map());
  const loaded = useRef(new Set<string>());
  const cell = cellOf(focus, DETAIL_LEVEL);
  const cellKey = cell ? cell.join(",") : "outside";

  useEffect(() => {
    // Re-derive the cell from its key so the effect depends only on the key.
    const parts = cellKey === "outside" ? null : cellKey.split(",").map(Number);
    const here: Vec3 | null = parts && parts.length === 3 ? [parts[0] ?? 0, parts[1] ?? 0, parts[2] ?? 0] : null;
    const wanted: [number, Vec3][] = [[0, [0, 0, 0]]];
    if (here) for (const c of neighbourhood(here, DETAIL_LEVEL)) wanted.push([DETAIL_LEVEL, c]);
    let cancelled = false;
    for (const [level, c] of wanted) {
      const key = `${level}/${c.join("/")}`;
      if (loaded.current.has(key)) continue;
      loaded.current.add(key);
      api
        .tile(level, c[0], c[1], c[2], TILE_LIMIT)
        .then((t) => {
          if (cancelled) return;
          setStars((prev) => {
            const next = new Map(prev);
            for (const s of t.stars) next.set(s.id, { p: [s.x_pc, s.y_pc, s.z_pc], g: s.phot_g_mean_mag });
            return next;
          });
        })
        .catch(() => loaded.current.delete(key));
    }
    return () => {
      cancelled = true;
    };
  }, [cellKey]);

  return stars;
}

function StarField({ stars, focus }: { stars: Map<number, Star>; focus: Vec3 }) {
  const { positions, colors } = useMemo(() => {
    const list = [...stars.values()];
    const pos = rebase(list.map((s) => s.p), focus);
    const col = new Float32Array(list.length * 3);
    list.forEach((s, i) => {
      // Illustrative brightness: brighter G magnitude -> lighter point. Not a physical colour.
      const b = s.g === null ? 0.35 : Math.min(1, Math.max(0.25, 1.15 - s.g / 18));
      col[i * 3] = b;
      col[i * 3 + 1] = b;
      col[i * 3 + 2] = Math.min(1, b + 0.08);
    });
    return { positions: pos, colors: col };
  }, [stars, focus]);
  return (
    <points key={positions.length}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
        <bufferAttribute attach="attributes-color" args={[colors, 3]} />
      </bufferGeometry>
      <pointsMaterial size={2} sizeAttenuation={false} vertexColors depthWrite={false} />
    </points>
  );
}

function Dot({ pos, focus, color, size }: { pos: Vec3; focus: Vec3; color: string; size: number }) {
  const arr = useMemo(() => rebase([pos], focus), [pos, focus]);
  return (
    <points>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[arr, 3]} />
      </bufferGeometry>
      <pointsMaterial size={size} sizeAttenuation={false} color={color} depthTest={false} />
    </points>
  );
}

/** Camera-relative position (float64 subtraction before any float32 conversion). */
function relative(p: Vec3, origin: Vec3): [number, number, number] {
  return [p[0] - origin[0], p[1] - origin[1], p[2] - origin[2]];
}

/** The two members of drei's OrbitControls the camera rig uses. */
interface Controls {
  target: { set: (x: number, y: number, z: number) => unknown };
  update: () => unknown;
}

/** Applies explicit zoom requests (buttons) and focus changes; wheel zoom is OrbitControls'. */
function CameraRig({ distance, nonce, focusKey }: { distance: number; nonce: number; focusKey: string }) {
  const camera = useThree((s) => s.camera);
  const controls = useThree((s) => s.controls) as unknown as Controls | null;
  useEffect(() => {
    const dir = camera.position.clone();
    if (dir.lengthSq() === 0) dir.set(0, 0, 1);
    camera.position.copy(dir.setLength(distance));
    controls?.target.set(0, 0, 0);
    controls?.update();
    // `nonce` is in the deps so an explicit request re-applies even at the same distance.
  }, [camera, controls, distance, nonce, focusKey]);
  return null;
}

function Bodies({
  bodies,
  focus,
  viewPc,
  labelLayer,
}: {
  bodies: readonly BodyMarker[];
  focus: Vec3;
  viewPc: number;
  labelLayer: React.RefObject<HTMLDivElement | null>;
}) {
  const groups = useMemo(() => labelGroups(bodies, viewPc), [bodies, viewPc]);
  return (
    <>
      {bodies.map((b) => (
        <Dot key={b.id} pos={b.pos} focus={focus} color={b.label === "Sun" ? "#ffd36b" : "#e8edf7"} size={b.label === "Sun" ? 8 : 5} />
      ))}
      {/* Labels only at planetary scales (< ~0.002 pc), where they are readable. */}
      {viewPc < 2e-3 &&
        groups.map((g) => (
          // A fixed portal target: without it drei mounts the first label before its default
          // target settles and leaves that label empty.
          <Html
            key={g.names.join("|")}
            portal={labelLayer as React.RefObject<HTMLElement>}
            position={relative(g.pos, focus)}
            style={{ pointerEvents: "none" }}
          >
            <span className="body-label">{g.names.join(", ")}</span>
          </Html>
        ))}
    </>
  );
}

export function GalaxyView({ focus, zoom, onViewDistance, bodies, selected, route, ship, reducedMotion }: Props) {
  const [viewPc, setViewPc] = useState(zoom.distancePc);
  const labelLayer = useRef<HTMLDivElement | null>(null);
  useEffect(() => setViewPc(zoom.distancePc), [zoom.distancePc, zoom.nonce]);
  const stars = useStars(focus);
  const routePts = useMemo(
    () => (route ? ([relative(route.a, focus), relative(route.b, focus)] as const) : null),
    [route, focus],
  );
  return (
    <div className="galaxy" role="img" aria-label={`3D view of ${stars.size} nearby stars centred on the current focus`}>
      <div ref={labelLayer} className="label-layer" aria-hidden="true" />
      <Canvas
        gl={{ logarithmicDepthBuffer: true, antialias: true }}
        camera={{ position: [0, 0, zoom.distancePc], near: 1e-10, far: 1e5, fov: 50 }}
        data-testid="galaxy-canvas"
      >
        <color attach="background" args={["#05070d"]} />
        <StarField stars={stars} focus={focus} />
        <Bodies bodies={bodies} focus={focus} viewPc={viewPc} labelLayer={labelLayer} />
        {selected && <Dot pos={selected.pos} focus={focus} color="#6bd0ff" size={8} />}
        {routePts && (
          <Line
            points={[routePts[0], routePts[1]]}
            color="#5fd38d"
            lineWidth={1.5}
          />
        )}
        {ship && <Dot pos={ship} focus={focus} color="#ff6b6b" size={9} />}
        <OrbitControls
          makeDefault
          enableDamping={!reducedMotion}
          minDistance={MIN_VIEW_PC}
          maxDistance={MAX_VIEW_PC}
          onChange={(e) => {
            const cam = (e?.target as { object?: { position: { length: () => number } } } | undefined)?.object;
            if (cam) {
              const d = cam.position.length();
              setViewPc(d);
              onViewDistance(d);
            }
          }}
        />
        <CameraRig distance={zoom.distancePc} nonce={zoom.nonce} focusKey={focus.join(",")} />
      </Canvas>
      <p className="overlay">
        <span className="state state-illustrative">Illustrative</span> point size and brightness. Positions:
        Gaia DR3 astrometry with Bailer-Jones (2021) geometric distances, ICRS axes, barycentric. {stars.size} stars
        loaded as octree tiles; Solar System bodies from JPL Horizons at the snapshot epoch. Gaia distances degrade
        beyond about 1–2 kpc; this view covers about 100 pc.
      </p>
    </div>
  );
}
