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

## Solar System (M3)

- Each Horizons response states its own reference frame (`ICRF`), start time
  (`A.D. 2016-Jan-01 12:00:00.0000 TDB`, i.e. JD 2457389.0 TDB) and the ephemeris source of
  the target and the centre: DE441 for most bodies, `mar099` for Mars, `jup365_merged` for
  the Galilean moons, `sat441l` for Titan, `plu060_merged` for Pluto and Charon. The build
  copies these verbatim, the database keeps them in `position_method` and `epoch`, and the UI
  shows them. Nothing is relabelled by hand.
- Bodies and stars share ICRS axes with a barycentric origin. Gaia positions are at J2016.0
  and the Horizons epoch is JD 2457389.0 TDB, as each source states.
- Distances from the Sun are derived (`astronomy_core.frames.separation`) at the shared
  snapshot epoch.
- **Floating origin, validated in `apps/web/src/lib/space.test.ts`:** focused near Earth
  (~5e-6 pc), Proxima (1.3 pc) and at Sgr A*'s distance (8122 pc), separations from 1 pc down
  to 1e-8 pc (Earth–Moon scale) keep an error below 1/1000 of the separation after rebasing.
  That is sub-pixel when the separation fills a 1000-px view.
  - The limit at 8122 pc is float64 itself: about 1.8e-12 pc resolution, so 1e-8 pc
    separations carry about 2e-4 relative error. That is still sub-pixel.
  - Without rebasing, absolute float32 at that distance loses even 0.2 AU separations. The
    test demonstrates this.
