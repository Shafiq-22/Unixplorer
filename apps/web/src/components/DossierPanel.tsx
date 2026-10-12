"use client";

import type { Dossier, Measurement, SourceRef } from "@atlas/shared-types";
import { fmt, formatUncertainty, formatValue, STATE_LABEL } from "@/lib/format";

interface Props {
  dossier: Dossier;
  onFocus: () => void;
  onSetOrigin: () => void;
  onSetDestination: () => void;
}

function Source({ s }: { s: SourceRef }) {
  return (
    <details className="source">
      <summary>source</summary>
      <dl>
        <dt>Archive</dt>
        <dd>{s.archive}</dd>
        <dt>Release</dt>
        <dd>{s.release}</dd>
        <dt>Retrieved</dt>
        <dd>{s.retrieved_at}</dd>
        <dt>Raw record</dt>
        <dd><code>{s.source_record_id}</code></dd>
        {s.publication && (
          <>
            <dt>Publication</dt>
            <dd>
              {s.publication.citation ?? ""} <code>{s.publication.bibcode}</code>
            </dd>
          </>
        )}
      </dl>
    </details>
  );
}

function StateBadge({ state }: { state: string }) {
  return <span className={`state state-${state}`}>{STATE_LABEL[state] ?? state}</span>;
}

function MeasurementRow({ m }: { m: Measurement }) {
  return (
    <tr data-quantity={m.quantity}>
      <th scope="row">
        {m.quantity}
        {m.is_default === true && <small> · default</small>}
        {m.solution_key && <small> · {m.solution_key}</small>}
      </th>
      <td>{formatValue(m)}</td>
      <td>{formatUncertainty(m)}</td>
      <td><StateBadge state={m.state} /></td>
      <td>{m.method}</td>
      <td><Source s={m.source} /></td>
    </tr>
  );
}

export function DossierPanel({ dossier, onFocus, onSetOrigin, onSetDestination }: Props) {
  const o = dossier.object;
  const pos = dossier.positions[0];
  const has3d = o.has_3d_position;
  return (
    <section aria-labelledby="dossier-title" data-testid="dossier">
      <h2 id="dossier-title">{o.display_name}</h2>
      <p className="lede">
        {o.object_type}
        {o.display_name !== o.primary_name && <> · {o.primary_name}</>}
      </p>
      <div className="actions">
        <button type="button" onClick={onFocus} disabled={!has3d}>Focus in 3D</button>
        <button type="button" onClick={onSetOrigin} disabled={!has3d} data-testid="set-origin">
          Set as origin
        </button>
        <button type="button" onClick={onSetDestination} disabled={!has3d} data-testid="set-destination">
          Set as destination
        </button>
      </div>
      {!has3d && (
        <p className="warn" role="note">
          No distance solution: shown in sky view only, not placed in 3D and not routable.
        </p>
      )}

      {pos && (
        <>
          <h3>Position</h3>
          <dl>
            <dt>Frame / epoch</dt>
            <dd>{pos.frame} · {pos.epoch}</dd>
            {pos.ra_deg !== null && pos.dec_deg !== null && (
              <>
                <dt>RA, Dec</dt>
                <dd>
                  {fmt(pos.ra_deg, 10)}°, {fmt(pos.dec_deg, 10)}°
                  {pos.ra_error_mas !== null && pos.dec_error_mas !== null &&
                    ` (± ${fmt(pos.ra_error_mas, 3)}, ± ${fmt(pos.dec_error_mas, 3)} mas)`}{" "}
                  <StateBadge state={pos.position_state} />
                </dd>
              </>
            )}
            <dt>Distance</dt>
            <dd data-testid="distance">
              {pos.distance ? (
                <>
                  {fmt(pos.distance.value_pc)} pc [{pos.distance.lower_pc === null ? "?" : fmt(pos.distance.lower_pc)} –{" "}
                  {pos.distance.upper_pc === null ? "?" : fmt(pos.distance.upper_pc)}] ({pos.distance.interval}){" "}
                  <StateBadge state={pos.distance.state} /> {pos.distance.method}
                  <Source s={pos.distance.source} />
                </>
              ) : (
                <StateBadge state={pos.distance_state} />
              )}
            </dd>
            {pos.cartesian && (
              <>
                <dt>x, y, z (ICRS, barycentric)</dt>
                <dd>
                  {fmt(pos.cartesian.x_pc)}, {fmt(pos.cartesian.y_pc)}, {fmt(pos.cartesian.z_pc)} pc{" "}
                  <StateBadge state="derived" /> {pos.cartesian.method}
                </dd>
              </>
            )}
            {pos.state_vector && (
              <>
                <dt>State vector</dt>
                <dd>
                  {fmt(pos.state_vector.x_km)}, {fmt(pos.state_vector.y_km)}, {fmt(pos.state_vector.z_km)} km;{" "}
                  {fmt(pos.state_vector.vx_km_s)}, {fmt(pos.state_vector.vy_km_s)}, {fmt(pos.state_vector.vz_km_s)} km/s{" "}
                  <StateBadge state={pos.position_state} />
                </dd>
              </>
            )}
            <dt>Position source</dt>
            <dd><Source s={pos.source} /></dd>
          </dl>
        </>
      )}

      <h3>Measurements</h3>
      {dossier.measurements.length === 0 ? (
        <p>No measurements in the snapshot.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">Quantity</th>
                <th scope="col">Value</th>
                <th scope="col">Uncertainty</th>
                <th scope="col">State</th>
                <th scope="col">Method</th>
                <th scope="col">Source</th>
              </tr>
            </thead>
            <tbody>
              {dossier.measurements.map((m) => (
                <MeasurementRow key={`${m.quantity}-${m.source.source_record_id}`} m={m} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {dossier.parent && (
        <p>
          Host: <strong>{dossier.parent.object.display_name}</strong> <small>({dossier.parent.reason})</small>
        </p>
      )}
      {dossier.children.length > 0 && (
        <p>Planets: {dossier.children.map((c) => c.display_name).join(", ")}</p>
      )}

      <details>
        <summary>Identifiers ({dossier.identifiers.length}) and aliases ({dossier.aliases.length})</summary>
        <ul>
          {dossier.identifiers.map((i) => (
            <li key={`${i.catalogue}-${i.identifier}`}>
              {i.catalogue}: {i.identifier}
            </li>
          ))}
        </ul>
        <p>{dossier.aliases.join(" · ")}</p>
      </details>
    </section>
  );
}
