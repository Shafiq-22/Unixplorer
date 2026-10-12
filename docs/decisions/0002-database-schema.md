# 0002: Database schema and load policy

- Status: accepted (M1)
- Date: 2026-10-12

## Context
CLAUDE.md §6 lists the initial tables and points to "spec §8" for field-level design. That
file (`docs/spec/universe-atlas-spec.md`) is not in the repository, so this ADR defines the
fields. Constraints come from §5 (provenance, null-not-zero, keep alternatives), §6 (value
model and states) and §7 (frames, distances).

## Decision

**Provenance is enforced in the schema, not only in code.**
- `scientific_source` holds one row per manifest entry loaded. `source_file` holds one row per
  manifest file (path, sha256, bytes, rows).
- Every scientific row has NOT NULL `source_file_id`, `source_row` and
  `source_record_id = "<raw path>#row=<n>"`, so a value cannot exist without its raw-file link.
  This covers measurement, position_solution, external_identifier, object_alias and
  classification.
- `atlas db load` additionally rejects any input row whose path is not a file of the latest
  *complete* manifest entry for its dataset, or whose row index is outside that file.

**Values (§6).**
- `measurement` has one row per quantity per source row: value, unit as the archive gave it,
  lower and upper uncertainty, `uncertainty_type`, `state`, `method`, `solution_key`,
  `is_default` (the archive's own flag), publication, and source columns.
- Check constraints: `state` must be one of the 11 states in §6; a null value only with
  state `unknown` or `not_applicable`; NaN is never stored.
- Alternatives are separate rows. For example, each NASA Exoplanet Archive solution is its own
  row with `solution_key` set to the solution's reference and `is_default` from `default_flag`.
- `uncertainty_type` is one of `symmetric_1sigma` (Gaia), `interval_bounds_p16_p84`
  (Bailer-Jones: the bounds themselves, not offsets), `asymmetric_offsets` (exoplanet
  err1/err2, stored as positive offsets), `upper_limit` or `lower_limit`.

**Positions (§5, §7).**
- `position_solution` is either an ICRS sky position at a stated epoch or a Horizons state
  vector.
- A distance is optional and carries its own source columns, because the Gaia position and
  the Bailer-Jones distance come from different files.
- Without a distance, `distance_state = 'unknown'` and the object is sky-view only. A check
  constraint ties `distance_pc IS NULL` to that state.
- **Distance selection policy (M1):** the adopted distance for a Gaia star is the Bailer-Jones
  *geometric* median with its 16th–84th percentile bounds (`bailer_jones_2021_geometric`). It
  depends only on the parallax and the Galactic prior; the photogeometric estimate also uses
  photometry and is missing for more stars. Both estimates are always stored as `measurement`
  rows, so the alternative stays visible.
- Landmarks get SIMBAD sky positions only: their literature distances are pending (§8.3).

**Objects and cross-matches.**
- `celestial_object.natural_key` (for example `gaia_dr3:<source_id>`,
  `exoplanet_archive:<pl_name>`, `horizons:<target>`) makes loads idempotent:
  `INSERT … ON CONFLICT DO NOTHING` everywhere.
- The SIMBAD↔Gaia cross-match matches on SIMBAD's own identifier `Gaia DR3 <source_id>`. One
  `provenance_event` records the method and reason, and every identifier, alias and
  classification it created points at that event. Deleting the rows with that
  `provenance_event_id` reverses the match (§5).
- A planet's `parent_object_id` is set only when the archive's `gaia_dr3_id` names a loaded Gaia
  star, and `parent_link_reason` records that.

**Routes.** `saved_route`, `route_calculation` (stores `frame_metadata()` and the full
`ModelResult` dicts) and `traversal_session` are created now and used from M2.

## Consequences
- Units stay as the archive gave them (mas, mas/yr, pc, km, km/s, Rearth…). Conversion to SI
  happens in `astronomy-core` at use time, so the database never holds a value the archive did
  not publish.
- Sky indexing (Q3C or pgSphere) is deferred to M2. Neither extension is installed in the
  development image.
