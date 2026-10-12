# Frames

Code: `packages/astronomy-core/astronomy_core/frames.py`.

## Pinned Galactocentric parameters

The 3D galaxy uses `astropy.coordinates.Galactocentric`, built explicitly from astropy's named
parameter set **`v4.0`** (`GALACTOCENTRIC_DEFAULTS`). It is never built from astropy's session
default, which `latest` could change in a future astropy release. Every `route_calculation`
stores the output of `frame_metadata()`.

Values below are as reported by astropy 8.0.1 at authoring time; they come from astropy's
registry, not from memory:

| Parameter | Value | Reference given by astropy |
|---|---|---|
| `galcen_distance` (R₀) | 8.122 kpc | 2018A&A...615L..15G |
| `z_sun` | 20.8 pc | 2019MNRAS.482.1417B |
| `galcen_coord` (Sgr A* direction) | astropy registry value | 2004ApJ...616..872R |
| `galcen_v_sun` | astropy registry value | 2018RNAAS...2..210D, 2018A&A...615L..15G, 2004ApJ...616..872R |
| `roll` | 0 deg | — |

`tests/scientific/test_frames.py` checks that:

- the frame matches astropy's `v4.0` set, and stays pinned even when astropy's session
  default is switched to another set;
- the distance between two positions is the same in heliocentric and galactocentric frames
  to `rel=1e-9`;
- Sgr A*'s direction placed at R₀ transforms to the galactocentric origin (within 1 µpc), and
  agrees with astropy's own transform to 1e-9 pc.

## Positions

- Stored: ICRS RA/Dec at the catalogue epoch (Gaia DR3: J2016.0), plus a separate distance
  solution.
- `icrs_position()` refuses to build a 3D position without a distance. An object with no
  distance solution belongs in the sky view only (CLAUDE.md §5).
- Solar System bodies come from Horizons: ICRF axes, barycentric, at J2016.0 TDB (see
  `data/queries/horizons_bodies.json`).
