"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Dossier, ObjectSummary, RouteResult, SolarSystem, Trajectory } from "@atlas/shared-types";
import { api, ApiError } from "@/lib/api";
import { AU_PER_PC, formatDistance } from "@/lib/format";
import { lerp3, type Vec3 } from "@/lib/space";
import { advance, viewAt, type ClockState } from "@/lib/traversalClock";
import { DossierPanel } from "./DossierPanel";
import { RoutePlanner } from "./RoutePlanner";
import { SolarSystemPanel } from "./SolarSystemPanel";
import { SearchBox } from "./SearchBox";
import { TraversalPanel } from "./TraversalPanel";

// React Three Fiber is client-only (CLAUDE.md §12).
const GalaxyView = dynamic(() => import("./GalaxyView").then((m) => m.GalaxyView), {
  ssr: false,
  loading: () => <div className="galaxy">Loading 3D view…</div>,
});

function xyz(d: Dossier | null): Vec3 | null {
  const c = d?.positions.find((p) => p.cartesian)?.cartesian;
  return c ? [c.x_pc, c.y_pc, c.z_pc] : null;
}

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mq.matches);
    const on = (e: MediaQueryListEvent) => setReduced(e.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return reduced;
}

interface Travel {
  id: number;
  trajectory: Trajectory;
  totalYr: number;
}

export function Explorer() {
  const reducedMotion = usePrefersReducedMotion();
  const [error, setError] = useState<string | null>(null);
  const [dossier, setDossier] = useState<Dossier | null>(null);
  const [system, setSystem] = useState<SolarSystem | null>(null);
  const [focus, setFocus] = useState<Vec3>([0, 0, 0]);
  // Start at planetary scale around the Sun; zoom spans Earth-Moon to stellar distances.
  const [zoom, setZoom] = useState({ distancePc: 3e-4, nonce: 0 });
  const [viewPc, setViewPc] = useState(3e-4);
  const [origin, setOrigin] = useState<{ o: ObjectSummary; p: Vec3 } | null>(null);
  const [destination, setDestination] = useState<{ o: ObjectSummary; p: Vec3 } | null>(null);
  const [route, setRoute] = useState<RouteResult | null>(null);
  const [travel, setTravel] = useState<Travel | null>(null);
  const [clock, setClock] = useState<ClockState | null>(null);
  const [rate, setRate] = useState(1);
  const rateRef = useRef(rate);
  rateRef.current = rate;

  const fail = (e: unknown) => setError(e instanceof ApiError ? e.message : "request failed");

  // The view starts centred on the Sun; Earth is the default route origin (M3).
  useEffect(() => {
    api
      .solarSystem()
      .then((ss) => {
        setSystem(ss);
        const sun = ss.bodies.find((b) => b.object.display_name === "Sun")?.position.cartesian;
        if (sun) setFocus([sun.x_pc, sun.y_pc, sun.z_pc]);
        const earth = ss.bodies.find((b) => b.object.display_name === "Earth");
        const ep = earth?.position.cartesian;
        if (earth && ep) setOrigin({ o: earth.object, p: [ep.x_pc, ep.y_pc, ep.z_pc] });
      })
      .catch(fail);
  }, []);

  const bodies = useMemo(
    () =>
      (system?.bodies ?? []).flatMap((b) => {
        const c = b.position.cartesian;
        return c ? [{ id: b.object.id, pos: [c.x_pc, c.y_pc, c.z_pc] as Vec3, label: b.object.display_name }] : [];
      }),
    [system],
  );
  const sunPos = bodies.find((b) => b.label === "Sun")?.pos ?? null;

  const select = useCallback((id: number) => {
    setError(null);
    api.dossier(id).then(setDossier).catch(fail);
  }, []);

  // Frame-rate-independent clock: wall-clock deltas feed `advance`; the view is derived.
  const status = clock?.status;
  useEffect(() => {
    if (!travel || status !== "running") return;
    let raf = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const dt = now - last;
      last = now;
      setClock((c) => (c ? advance(c, dt, rateRef.current, travel.totalYr) : c));
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [travel, status]);

  useEffect(() => {
    if (travel && status === "arrived") {
      api.updateTraversal(travel.id, { status: "arrived", coordinate_time_yr: travel.totalYr }).catch(fail);
    }
  }, [travel, status]);

  const view = travel && clock ? viewAt(travel.trajectory.samples, clock.simTimeYr) : null;
  const routeLine = useMemo(
    () => (route && origin && destination ? { a: origin.p, b: destination.p } : null),
    [route, origin, destination],
  );
  const ship = routeLine && view ? lerp3(routeLine.a, routeLine.b, view.fraction) : null;

  async function startTravel(modelId: string) {
    if (!route) return;
    try {
      const [trajectory, t] = await Promise.all([
        api.trajectory(route.id, modelId),
        api.startTraversal(route.id, modelId),
      ]);
      const totalYr = trajectory.samples[trajectory.samples.length - 1]?.coordinate_time_yr ?? 0;
      setRate(totalYr / 20); // whole trip in about 20 s by default
      setTravel({ id: t.id, trajectory, totalYr });
      setClock({ simTimeYr: 0, status: "running" });
    } catch (e: unknown) {
      fail(e);
    }
  }

  function setStatus(next: "running" | "paused" | "cancelled") {
    if (!travel || !clock) return;
    setClock({ ...clock, status: next });
    api.updateTraversal(travel.id, { status: next, coordinate_time_yr: clock.simTimeYr }).catch(fail);
  }

  const selectedPos = xyz(dossier);
  // The camera rig applies the requested distance exactly, so it is also the new current one
  // (OrbitControls only reports wheel/drag changes, not programmatic ones).
  const requestZoom = (distancePc: number) => {
    setZoom((z) => ({ distancePc, nonce: z.nonce + 1 }));
    setViewPc(distancePc);
  };

  return (
    <div className="explorer">
      <aside>
        <h1>Universe Atlas</h1>
        <p className="lede">
          Milky Way edition · solar neighbourhood from the 2026-10-12 snapshot · <a href="/health">health</a>
        </p>
        <SearchBox label="Find an object" onSelect={(o) => select(o.id)} testId="search" />
        {error && <p className="bad" role="alert">{error}</p>}
        <div className="actions" aria-label="3D view controls">
          <button type="button" onClick={() => sunPos && setFocus(sunPos)} disabled={!sunPos}>
            Focus Sun
          </button>
          <button type="button" onClick={() => selectedPos && setFocus(selectedPos)} disabled={!selectedPos}>
            Focus selection
          </button>
          <button type="button" onClick={() => requestZoom(Math.max(viewPc / 4, 2e-9))} aria-label="Zoom in" data-testid="zoom-in">
            Zoom +
          </button>
          <button type="button" onClick={() => requestZoom(Math.min(viewPc * 4, 2000))} aria-label="Zoom out" data-testid="zoom-out">
            Zoom −
          </button>
          <button type="button" onClick={() => requestZoom(3e-4)}>Planets</button>
          <button type="button" onClick={() => requestZoom(4)}>Nearby stars</button>
          <span className="muted" data-testid="view-radius" data-pc={viewPc}>
            camera {formatDistance(viewPc, viewPc * AU_PER_PC)} from focus
          </span>
        </div>
        {dossier && (
          <DossierPanel
            dossier={dossier}
            onFocus={() => selectedPos && setFocus(selectedPos)}
            onSetOrigin={() => {
              if (selectedPos) setOrigin({ o: dossier.object, p: selectedPos });
              setRoute(null);
            }}
            onSetDestination={() => {
              if (selectedPos) setDestination({ o: dossier.object, p: selectedPos });
              setRoute(null);
            }}
          />
        )}
        {system && <SolarSystemPanel system={system} onSelect={select} />}
        <RoutePlanner
          origin={origin?.o ?? null}
          destination={destination?.o ?? null}
          route={route}
          onRoute={(r) => {
            setRoute(r);
            setTravel(null);
            setClock(null);
          }}
          onTravel={startTravel}
          travelling={status === "running" || status === "paused"}
        />
        {travel && clock && view && (
          <TraversalPanel
            trajectory={travel.trajectory}
            view={view}
            status={clock.status}
            yearsPerSecond={rate}
            onRate={setRate}
            onPause={() => setStatus("paused")}
            onResume={() => setStatus("running")}
            onCancel={() => setStatus("cancelled")}
          />
        )}
      </aside>
      <main>
        <GalaxyView
          focus={focus}
          zoom={zoom}
          onViewDistance={setViewPc}
          bodies={bodies}
          selected={selectedPos && dossier ? { pos: selectedPos, label: dossier.object.display_name } : null}
          route={routeLine}
          ship={ship}
          reducedMotion={reducedMotion}
        />
      </main>
    </div>
  );
}
