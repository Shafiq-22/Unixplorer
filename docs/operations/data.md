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
| 2026-10-12 | M0 tooling committed; all fetches blocked by egress policy (HTTP 403 at proxy for every archive host) | no raw data; manifest + queries only |

## Hosts the environment must allow

`gea.esac.esa.int`, `simbad.cds.unistra.fr`, `ssd.jpl.nasa.gov`,
`exoplanetarchive.ipac.caltech.edu`, and for §8.3 literature checks `api.adsabs.harvard.edu`
(needs an ADS token in `.env`) and `tapvizier.cds.unistra.fr`.
