---
name: scientific-provenance-and-validation
description: Rules for keeping every scientific value traceable to an archive file, and for literature (transcribed) values. Use when adding datasets, landmark distances, or any code that stores or shows a scientific number.
---

# Scientific provenance and validation

- Every value must trace to `data/raw/<file>` through `source_record_id` (`<path>#row=<n>`) and a
  manifest entry. A row without one is rejected.
- A missing value is `null` with state `unknown`. The build turns NaN and masked cells into null.
  Never write 0 or a default instead.
- Keep each value's original unit. Normalised values go in a separate column (`__si`) and never
  overwrite the original.
- Identifiers (SIMBAD ids, Horizons IDs) are verified by the fetch itself: the `TAP_SCHEMA`
  check, the Horizons target-name check, and recording landmark ids that did not resolve. A
  failed verification makes the snapshot partial. Never patch around one.
- Literature values (§8.3): the bibcode must resolve in NASA ADS, with the ADS response saved
  under `data/raw/ads/`. Record the table, page or equation, the value, its uncertainty and unit
  in `data/raw/literature/<bibcode>.yaml` with `method: transcribed`, and list the value in the
  milestone report for a human to check. Use a VizieR table for the paper when one exists.
- Synthetic values are allowed only in `tests/fixtures/` and must be labelled SYNTHETIC.
