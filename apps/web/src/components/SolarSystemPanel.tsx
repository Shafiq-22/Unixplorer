"use client";

import type { SolarSystem } from "@atlas/shared-types";
import { fmt } from "@/lib/format";

interface Props {
  system: SolarSystem;
  onSelect: (objectId: number) => void;
}

export function SolarSystemPanel({ system, onSelect }: Props) {
  return (
    <section aria-labelledby="ss-title" data-testid="solar-system">
      <h2 id="ss-title">Solar System</h2>
      <p data-testid="snapshot-epoch">
        Positions at <strong>{system.epoch}</strong>, as stated by JPL Horizons for this snapshot.
      </p>
      <p><small>{system.frame}</small></p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">Body</th>
              <th scope="col">Distance from Sun</th>
              <th scope="col">Ephemeris</th>
            </tr>
          </thead>
          <tbody>
            {system.bodies.map((b) => (
              <tr key={b.object.id}>
                <th scope="row">
                  <button type="button" className="link" onClick={() => onSelect(b.object.id)}>
                    {b.object.display_name}
                  </button>
                </th>
                <td>
                  {b.distance_from_sun ? (
                    <>
                      {fmt(b.distance_from_sun.value_au)} AU <span className="state state-derived">derived</span>
                    </>
                  ) : (
                    "—"
                  )}
                </td>
                <td><small>{b.position.position_method}</small></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
