# Data snapshot operations

## Commands

```bash
uv sync
uv run atlas data status                 # what is downloaded, when, from which release
uv run atlas data fetch <dataset>        # one of the ids in ingestion/datasets.py
uv run atlas data verify                 # sha256 + bytes + rows for every manifest file
uv run atlas data build                  # data/raw -> data/processed/*.parquet (deterministic)
```

Fetch order: `gaia_dr3_nearby` → `gaia_dr3_distances` → `simbad_ids` (needs the Gaia snapshot)
→ `horizons_bodies` → `landmarks` → `exoplanets_ps`. Then `verify`, then `build`.

Every fetch first queries the archive's own `TAP_SCHEMA.columns` for each table it uses and
aborts if a column is missing; that response is kept as a `schema_check` file in the snapshot.
A failed or interrupted fetch is still recorded in `data/manifest.yaml` as `partial: <reason>`.

## Size log

| Date (UTC) | Event | Total `data/` size |
|---|---|---|
| 2026-10-12 07:40 | M0 tooling committed; every fetch blocked by egress policy (HTTP 403) | manifest and queries only |
| 2026-10-12 10:05 | All six M0 datasets fetched, verified and built | 528 MB on disk: raw ≈ 388 MB (gaia 92 MB, simbad 242 MB, exoplanet_archive 54 MB, horizons 0.2 MB) + processed ≈ 148 MB (not committed) |

## Snapshot of 2026-10-12

| Dataset | Snapshot dir | Data files | Rows | Raw bytes |
|---|---|---|---|---|
| `gaia_dr3_nearby` | `data/raw/gaia/gaia_dr3_nearby/2026-10-12.5/` | 48 chunks | 372 226 | 73 409 421 |
| `gaia_dr3_distances` | `data/raw/gaia/gaia_dr3_distances/2026-10-12.2/` | 48 chunks | 372 226 | 21 409 866 |
| `simbad_ids` | `data/raw/simbad/simbad_ids/2026-10-12/` | 373 batches | 1 538 191 (alias rows; 249 432 of 372 226 Gaia sources matched) | 252 319 603 |
| `horizons_bodies` | `data/raw/horizons/horizons_bodies/2026-10-12/` | 18 JSON | 18 bodies | 119 044 |
| `landmarks` | `data/raw/simbad/landmarks/2026-10-12.2/` | 1 | 263 (10 landmarks × aliases) | 44 046 |
| `exoplanets_ps` | `data/raw/exoplanet_archive/exoplanets_ps/2026-10-12/` | 1 | 5 504 solutions (1 797 planets, 1 231 hosts) | 55 871 111 |

Raw byte totals include each snapshot's request and schema-check files. Per-file sha256 values
are in `data/manifest.yaml`.

Earlier attempts on the same day are kept, recorded as `partial`, in their own directories
(`.2`, `.3`, …). They include the async Gaia jobs that ran about an hour and then failed or were
aborted, which led to the chunked approach.

### Processed Parquet (not committed; `uv run atlas data build` reproduces these bytes)

Built with the locked dependencies in `uv.lock`. Rebuilding gave byte-identical files.

```
f581843625dd833693f84e7991a9e9ca1803c7ae7d4c161d568f640950d899a6  exoplanets_ps.parquet
cff2971237822c6df8eac5bcb56b2a249bcc39c8d74a53c1eb588c69eed09b79  gaia_dr3_distances.parquet
4d862ad165455f8fe835f91d1a3312d2c1f3fe115c1cfccaeb478567719f4442  gaia_dr3_nearby.parquet
f779785ca8b1b3a5144bc3731ac328b7d094e66c52101f8daf0009244ed07ae7  horizons_bodies.parquet
ff3716a0a63e23e0f9e952c742553db98b8246d82af19eae77cea541ccd0d6e0  landmarks.parquet
c6ea0cea9d62f18fa2d465cc1c9ec7e38134c73427e4633f0b924f07d3c9adf8  simbad_ids.parquet
```

## Git LFS budget

The raw Gaia, SIMBAD-id and exoplanet VOTables (about 388 MB) are stored in Git LFS. GitHub's
free LFS tier is about 1 GB of storage and 1 GB of bandwidth per month, so CI restores LFS
objects from the Actions cache rather than downloading them on every run. A second full snapshot
would roughly double LFS storage, so plan re-downloads with that in mind.

## Gaia Archive notes

- One async query over all of `gaiadr3.gaia_source` with `parallax > 10` ran for about an
  hour and then failed server-side (UWS file-quota lock timeout on the shared anonymous
  account). The fetch now issues 48 sync queries over disjoint `source_id` ranges. `source_id`
  is indexed and grows with sky position, and the set took about 11 minutes.
- The first and last chunks are open-ended, so the ranges cover every possible `source_id`
  (tested in `tests/unit/test_registry.py`).
- `QUERY_STATUS=OVERFLOW` (a truncated result) is rejected.
- Gaia returns `SOURCE_ID` in upper case. Processed column names are lower-cased, and each
  field's metadata keeps `original_name`.
