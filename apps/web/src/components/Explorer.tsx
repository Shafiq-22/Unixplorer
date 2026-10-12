"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Dossier, ObjectSummary, RouteResult, Trajectory } from "@atlas/shared-types";
import { api, ApiError } from "@/lib/api";
import { lerp3, type Vec3 } from "@/lib/space";
import { advance, viewAt, type ClockState } from "@/lib/traversalClock";
import { DossierPanel } from "./DossierPanel";
import { RoutePlanner } from "./RoutePlanner";
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
  const [sun, setSun] = useState<Dossier | null>(null);
  const [focus, setFocus] = useState<Vec3>([0, 0, 0]);
  const [viewDistance, setViewDistance] = useState(4);
  const [origin, setOrigin] = useState<{ o: ObjectSummary; p: Vec3 } | null>(null);
  const [destination, setDestination] = useState<{ o: ObjectSummary; p: Vec3 } | null>(null);
  const [route, setRoute] = useState<RouteResult | null>(null);
  const [travel, setTravel] = useState<Travel | null>(null);
  const [clock, setClock] = useState<ClockState | null>(null);
  const [rate, setRate] = useState(1);
  const rateRef = useRef(rate);
  rateRef.current = rate;

  const fail = (e: unknown) => setError(e instanceof ApiError ? e.message : "request failed");

  // The Sun is the default origin and the initial focus (M2: view centred on the Sun).
  useEffect(() => {
    api
      .search("sun")
      .then(async (r) => {
        const s = r.results.find((x) => x.display_name === "Sun");
        if (!s) return;
        const d = await api.dossier(s.id);
        setSun(d);
        const p = xyz(d);
        if (p) {
          setFocus(p);
          setOrigin({ o: d.object, p });
        }
      })
      .catch(fail);
  }, []);

  const select = useCallback((o: ObjectSummary) => {
    setError(null);
    api.dossier(o.id).then(setDossier).catch(fail);
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
  const sunPos = xyz(sun);

  return (
    <div className="explorer">
      <aside>
        <h1>Universe Atlas</h1>
        <p className="lede">
          Milky Way edition · solar neighbourhood from the 2026-10-12 snapshot · <a href="/health">health</a>
        </p>
        <SearchBox label="Find an object" onSelect={select} testId="search" />
        {error && <p className="bad" role="alert">{error}</p>}
        <div className="actions" aria-label="3D view controls">
          <button type="button" onClick={() => sunPos && setFocus(sunPos)} disabled={!sunPos}>
            Focus Sun
          </button>
          <button type="button" onClick={() => selectedPos && setFocus(selectedPos)} disabled={!selectedPos}>
            Focus selection
          </button>
          <button type="button" onClick={() => setViewDistance((d) => d / 2)} aria-label="Zoom in">Zoom +</button>
          <button type="button" onClick={() => setViewDistance((d) => d * 2)} aria-label="Zoom out">Zoom −</button>
          <span className="muted">view radius {viewDistance.toPrecision(3)} pc</span>
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
          viewDistancePc={viewDistance}
          sun={sunPos}
          selected={selectedPos && dossier ? { pos: selectedPos, label: dossier.object.display_name } : null}
          route={routeLine}
          ship={ship}
          reducedMotion={reducedMotion}
        />
      </main>
    </div>
  );
}
