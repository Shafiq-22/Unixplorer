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

Build version 2. M3 added the per-body Horizons header columns (ephemeris sources, reference
frame, start time); the version is stored in every file's metadata, so all hashes changed.
Rebuilding gives byte-identical files.

```
d603869b36502a9aaa01d9b987dbffcfbf500353250edea1a4319423d44af006  exoplanets_ps.parquet
11bd52db745c3b15a5ed6791f677caaddc8bca16ec6e0533fb2d6be09241f94c  gaia_dr3_distances.parquet
64919c3e672dfa78ca3ee5e5d60c428f29c38211c7d81bb95ae260ee844a38f9  gaia_dr3_nearby.parquet
57654b2cd9bf10e943abf93662628b6d26ee92a4f065706c95f68a672a2a0ea2  horizons_bodies.parquet
7e47758aa6ee76c31f9054abb143b4b86820d43bf8bc7c925debe5d6ffda6e8d  landmarks.parquet
67f9e42923645035505c2ef14e8d644fb545111e3e142d19bd094867a2b84efe  simbad_ids.parquet
```

A database loaded before a build-version change keeps its old rows, because `atlas db load`
only inserts. To pick up changed provenance text, reload into an empty schema.

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
