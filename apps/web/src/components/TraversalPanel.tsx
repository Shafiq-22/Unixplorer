"use client";

import type { Trajectory } from "@atlas/shared-types";
import { fmt, formatDuration } from "@/lib/format";
import type { ClockStatus, TraversalView } from "@/lib/traversalClock";

interface Props {
  trajectory: Trajectory;
  view: TraversalView;
  status: ClockStatus;
  yearsPerSecond: number;
  onRate: (r: number) => void;
  onPause: () => void;
  onResume: () => void;
  onCancel: () => void;
}

export function TraversalPanel({ trajectory, view, status, yearsPerSecond, onRate, onPause, onResume, onCancel }: Props) {
  const total = trajectory.samples[trajectory.samples.length - 1]?.coordinate_time_yr ?? 0;
  const speculative = trajectory.status === "speculative";
  return (
    <section aria-labelledby="trav-title" data-testid="traversal">
      <h2 id="trav-title">
        Traversal <small><code>{trajectory.model_id}</code></small>
        {speculative && <span className="state state-illustrative"> Speculative</span>}
      </h2>
      <p aria-live="polite">
        Status: <strong data-testid="traversal-status">{status}</strong>
      </p>
      <progress max={1} value={view.fraction} aria-label="route covered" />
      <dl>
        <dt>Coordinate time</dt>
        <dd>
          <span data-testid="coordinate-time" data-years={view.coordinateTimeYr}>{formatDuration(view.coordinateTimeYr)}</span> of{" "}
          {formatDuration(total)}
        </dd>
        <dt>Proper (ship) time</dt>
        <dd>{view.properTimeYr === null ? "not defined by this model" : formatDuration(view.properTimeYr)}</dd>
        <dt>Route covered</dt>
        <dd>{(view.fraction * 100).toFixed(2)} %</dd>
        <dt>Speed</dt>
        <dd>{fmt(view.speedC, 4)} c</dd>
      </dl>
      <p><small>Values interpolated between {trajectory.samples.length} states computed by the backend model.</small></p>
      <label>
        Time compression: {formatDuration(yearsPerSecond)} per second
        <input
          type="range"
          min={Math.log10(total / 600 || 1e-6)}
          max={Math.log10(total / 2 || 1)}
          step="0.01"
          value={Math.log10(yearsPerSecond)}
          onChange={(e) => onRate(10 ** Number(e.target.value))}
        />
      </label>
      <div className="actions">
        {status === "running" && <button type="button" onClick={onPause} data-testid="pause">Pause</button>}
        {status === "paused" && <button type="button" onClick={onResume} data-testid="resume">Resume</button>}
        {(status === "running" || status === "paused") && (
          <button type="button" onClick={onCancel} data-testid="cancel">Cancel</button>
        )}
      </div>
    </section>
  );
}
