"use client";

import { useState } from "react";
import type { ObjectSummary, RouteResult } from "@atlas/shared-types";
import { api, ApiError } from "@/lib/api";
import { fmt, formatOutput } from "@/lib/format";

interface Props {
  origin: ObjectSummary | null;
  destination: ObjectSummary | null;
  route: RouteResult | null;
  onRoute: (r: RouteResult) => void;
  onTravel: (modelId: string) => void;
  travelling: boolean;
}

const MODEL_LABEL: Record<string, string> = {
  classical_constant_speed: "Classical (Newtonian), constant speed",
  sr_inertial: "Special relativity, constant speed",
  sr_constant_proper_accel: "Special relativity, constant proper acceleration (flip at midpoint)",
  null_propagation: "Light signal (v = c)",
  hypothetical_ftl_effective: "Hypothetical faster-than-light (speculative)",
};

export function RoutePlanner({ origin, destination, route, onRoute, onTravel, travelling }: Props) {
  // Free numeric inputs: values are never clamped (v >= c is refused by the SR models, shown below).
  const [speed, setSpeed] = useState("0.5");
  const [accel, setAccel] = useState("1");
  const [ftl, setFtl] = useState("10");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [model, setModel] = useState("sr_constant_proper_accel");

  async function calculate() {
    if (!origin || !destination) return;
    const v = Number(speed);
    const a = Number(accel);
    const f = Number(ftl);
    if ([v, a, f].some((n) => !Number.isFinite(n) || n <= 0)) {
      setError("speeds and acceleration must be positive numbers");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      onRoute(
        await api.createRoute({
          origin_id: origin.id,
          destination_id: destination.id,
          speed_fraction_c: v,
          proper_acceleration_g: a,
          ftl_speed_fraction_c: f,
        }),
      );
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : "route calculation failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="route-title" data-testid="route-planner">
      <h2 id="route-title">Space GPS</h2>
      <dl>
        <dt>Origin</dt>
        <dd data-testid="route-origin">{origin?.display_name ?? "choose an object and press “Set as origin”"}</dd>
        <dt>Destination</dt>
        <dd data-testid="route-destination">
          {destination?.display_name ?? "choose an object and press “Set as destination”"}
        </dd>
      </dl>
      <div className="form-grid">
        <label>
          Cruise speed (× c) <small>classical &amp; SR inertial</small>
          <input type="number" min="0" step="any" value={speed} onChange={(e) => setSpeed(e.target.value)} data-testid="speed" />
        </label>
        <label>
          Proper acceleration (× g) <small>SR accel/decel</small>
          <input type="number" min="0" step="any" value={accel} onChange={(e) => setAccel(e.target.value)} />
        </label>
        <label>
          Effective speed (× c) <small>speculative FTL</small>
          <input type="number" min="0" step="any" value={ftl} onChange={(e) => setFtl(e.target.value)} />
        </label>
      </div>
      <button type="button" onClick={calculate} disabled={!origin || !destination || busy} data-testid="calculate">
        {busy ? "Calculating…" : "Calculate route"}
      </button>
      {error && <p className="bad" role="alert">{error}</p>}

      {route && (
        <div data-testid="route-results">
          <h3>
            {route.origin.object.display_name} → {route.destination.object.display_name}
          </h3>
          <p>
            Distance <strong data-testid="route-distance">{fmt(route.distance.value_pc)} pc</strong> (range{" "}
            {fmt(route.distance.lower_pc)} – {fmt(route.distance.upper_pc)} pc). <small>{route.distance.method}.</small>
          </p>
          <p>
            <small>
              Frame: astropy Galactocentric {String(route.frame["galactocentric_defaults"] ?? "?")}, astropy{" "}
              {String(route.frame["astropy_version"] ?? "?")}. Origin epoch {route.origin.epoch}; destination epoch{" "}
              {route.destination.epoch}. Route #{route.id}, {route.code_version}.
            </small>
          </p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">Model</th>
                  <th scope="col">Coordinate time</th>
                  <th scope="col">Proper (ship) time</th>
                  <th scope="col">Range over distance uncertainty</th>
                  <th scope="col">Notes</th>
                </tr>
              </thead>
              <tbody>
                {route.models.map((m) => {
                  const out = m.outputs ?? {};
                  const t = out["coordinate_time"] ?? out["effective_coordinate_time"];
                  const tLo = m.at_distance_lower?.["coordinate_time"] ?? m.at_distance_lower?.["effective_coordinate_time"];
                  const tHi = m.at_distance_upper?.["coordinate_time"] ?? m.at_distance_upper?.["effective_coordinate_time"];
                  return (
                    <tr key={m.model_id} data-model={m.model_id} className={m.status === "speculative" ? "speculative" : undefined}>
                      <th scope="row">
                        {MODEL_LABEL[m.model_id] ?? m.model_id}
                        {m.status === "speculative" && <span className="state state-illustrative"> Speculative</span>}
                        <br />
                        <small><code>{m.model_id}</code>{m.model_version ? ` v${m.model_version}` : ""}</small>
                      </th>
                      {m.refused ? (
                        <td colSpan={4} className="warn">Not applicable to these inputs: {m.refused}</td>
                      ) : (
                        <>
                          <td>{formatOutput(t)}</td>
                          <td>{formatOutput(out["proper_time"])}</td>
                          <td>{tLo && tHi ? `${formatOutput(tLo)} – ${formatOutput(tHi)}` : "—"}</td>
                          <td>
                            {out["lorentz_factor"] !== undefined && <>γ = {formatOutput(out["lorentz_factor"])}<br /></>}
                            {out["peak_lorentz_factor"] !== undefined && <>peak γ = {formatOutput(out["peak_lorentz_factor"])}<br /></>}
                            {m.warnings.map((w) => (
                              <span key={w} className="warn">{w}<br /></span>
                            ))}
                            <details>
                              <summary>assumptions ({m.assumptions.length})</summary>
                              <ul>{m.assumptions.map((a) => <li key={a}>{a}</li>)}</ul>
                            </details>
                          </td>
                        </>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <fieldset disabled={travelling}>
            <legend>Travel with</legend>
            {route.models.filter((m) => !m.refused).map((m) => (
              <label key={m.model_id} className="radio">
                <input type="radio" name="model" value={m.model_id} checked={model === m.model_id} onChange={() => setModel(m.model_id)} />
                {MODEL_LABEL[m.model_id] ?? m.model_id}
              </label>
            ))}
            <button
              type="button"
              data-testid="travel"
              onClick={() => onTravel(model)}
              disabled={route.models.find((m) => m.model_id === model)?.refused != null}
            >
              Travel
            </button>
          </fieldset>
        </div>
      )}
    </section>
  );
}
