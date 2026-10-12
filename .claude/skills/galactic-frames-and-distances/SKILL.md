---
name: galactic-frames-and-distances
description: Frames, epochs and distance solutions for placing objects in 3D and measuring between them (ICRS barycentric, pinned Galactocentric v4.0, Bailer-Jones adoption, route-distance ranges). Use for anything that positions objects or computes separations.
---

# Galactic frames and distances

- **Positions:** stored as ICRS RA/Dec at the catalogue epoch plus a separate distance. 3D
  positions are derived by `astronomy_core.frames.icrs_barycentric_xyz` (ICRS axes, origin at
  the Solar System barycentre, parsecs).
  - Horizons state vectors share those axes (`state_vector_xyz`). Both are at J2016.0 by
    design.
- **Galactocentric frame:** `galactocentric_frame()` uses astropy's `v4.0` parameters,
  explicitly. Record `frame_metadata()` with every route.
- **No distance means no 3D position:** sky view only, and no route. `icrs_position` and the
  routes API both refuse.
- **Distance policy:** the adopted distance is Bailer-Jones (2021) geometric with its
  16th–84th percentile bounds. Photogeometric is kept as an alternative measurement.
  - Never use 1/parallax when `parallax_over_error < 5` or the parallax is ≤ 0
    (`inverse_parallax_distance` refuses).
- **Route distance:** `route_planner.geometry.route_distance` gives the straight-line distance
  between adopted positions, with the exact min/max over each endpoint's distance interval
  along its line of sight.
  - The max is at the corners; the min uses the exact segment–segment closest-point method.
- **Data gaps:** very bright stars (Sirius A, Alpha Centauri A/B) are missing from Gaia DR3.
  The UI shows what the snapshot has; never fill gaps from memory.
- **Tests:** heliocentric and galactocentric separations must agree to 1e-9 relative. Compare
  transforms against astropy directly.
