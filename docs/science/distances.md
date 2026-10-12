# Distances

Code: `astronomy_core/distances.py`, `route_planner/geometry.py`.

## Adopted distance for Gaia stars

- **Policy:** Bailer-Jones et al. (2021) *geometric* median with its 16th–84th percentile
  bounds (`bailer_jones_2021_geometric`).
- **Alternative:** the *photogeometric* estimate is also stored as a measurement and shown in
  the dossier.
- **Rationale:** the geometric estimate uses the parallax and the Galactic prior only. The
  photogeometric one also uses photometry and is missing for more stars.
- See ADR 0002.

## 1/parallax

`inverse_parallax_distance` refuses parallax ≤ 0 or `parallax_over_error < 5` (CLAUDE.md §7).
It is not used for the adopted distance.

## Route distance and its range

- **Distance:** the straight line between adopted positions on ICRS axes, barycentric.
- **Range:** each endpoint with a distance interval may lie anywhere on its line of sight
  between the interval bounds. The reported range is the exact minimum and maximum of the
  separation over those segments, with the directions held fixed.
  - The maximum is at a pair of segment ends, since the distance is convex.
  - The minimum uses the clamped closest-points algorithm, checked against brute force in
    `tests/scientific/test_route_planner.py`.
- **Times:** each model's travel times are also evaluated at both range bounds.

## Known gaps

- Gaia DR3 lacks some very bright stars (for example Sirius A and Alpha Centauri A/B). They are
  absent from the snapshot, and the UI does not fill them in.
- Landmarks (Sgr A\*, clusters, nebulae) have no distance until literature values are added
  under §8.3, so they are sky-only.
