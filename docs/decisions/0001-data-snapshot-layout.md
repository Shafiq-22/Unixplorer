# 0001: Data snapshot layout, verification and build

- Status: accepted (M0)
- Date: 2026-10-12

## Context
CLAUDE.md §1 and §8 require every scientific value to trace back to an archive response saved
unmodified under `data/raw/`, with a manifest entry, before any app code exists.

## Decision
- **Python package `ingestion`, CLI `atlas`** (argparse, no extra framework). Dependencies:
  astropy (VOTable parsing, units), pyarrow (Parquet), requests, PyYAML.
- **Raw TAP over HTTP instead of astroquery** for fetches, so the saved bytes are exactly what
  the service returned (astroquery re-parses results). The IVOA TAP sync and UWS async
  protocols are implemented in about 150 lines (`ingestion/connectors/tap.py`).
- **Schema pre-flight.** Column and table names could not be verified against the documentation
  when this code was written, so every fetch checks them against the service's own
  `TAP_SCHEMA` and stores that response as evidence.
- **Snapshots** live in `data/raw/<source>/<dataset>/<YYYY-MM-DD>/` and are never overwritten. A
  second fetch on the same day is refused.
- **Manifest** is a YAML list with one entry per fetch attempt, including failed ones. Each file
  has a `role`: `data` (rows feed the build), `request` (the exact query or URL sent) or
  `schema_check`.
- **Build** writes one Parquet file per dataset from the latest *complete* snapshot. It uses zstd,
  embeds no timestamps and keeps raw row order, so its output is byte-identical (this is tested).
  Original values and units are kept; `<col>__si` companions come from `astropy.units` `.si`.
  Magnitudes and epochs get no companion. NaN and masked values become null.
  `source_record_id = "<raw path>#row=<n>"`.
- **Horizons epoch** is J2016.0 (JD 2457389.0 TDB), the Gaia DR3 reference epoch, barycentric
  ICRF. That puts stars and planets at the same epoch.
- **Git LFS** holds the Gaia, SIMBAD-id and exoplanet VOTables and the processed Parquet files.

## Consequences
- `atlas data verify` can run in CI with no network access.
- `exoplanets_ps` is fetched as a `sy_dist < 120` pc superset. Narrowing it to hosts in the Gaia
  set is a pipeline cross-match that still has to be written once the real `ps` columns are
  known.
