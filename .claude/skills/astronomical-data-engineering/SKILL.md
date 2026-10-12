---
name: astronomical-data-engineering
description: How catalogue data flows from the loaded Postgres snapshot to API responses (search, dossier, tiles), and how to add a new quantity or dataset to the database without losing provenance. Use when touching ingestion/dbload.py, the schema, or read endpoints.
---

# Astronomical data engineering

- **Pipeline:** `data/raw` → `atlas data build` (Parquet) → `atlas db load` → Postgres → API.
  The app reads only the database (CLAUDE.md §8.4).
- **New quantity:** add it to the loader's list for that dataset (e.g. `GAIA_MEASURES` in
  `ingestion/dbload.py`), keeping the archive's unit and `method`, and choose `state` from the
  11 §6 states.
  - Null or NaN becomes `state='unknown'`, `value=NULL`; the check constraints refuse anything
    else.
- **Schema change:** edit `database/atlas_db/models.py`, then `uv run alembic revision
  --autogenerate`, then review the file by hand. Autogenerate misses `CREATE EXTENSION` and
  check constraints, and must not import models.
  - Finish with `uv run alembic check`.
- **Derived values** (such as `bary_x_pc`) are computed by `astronomy_core` inside the loader,
  carry `derived_method`, and are never edited by hand.
- **Read endpoints** return every scientific value with its unit, uncertainty (with type), state,
  method and `SourceRef` (raw record, archive, release, retrieval time, publication). A number
  without these is a bug.
- **Search** uses the trigram index on `object_alias.alias_normalized`.
  - Ranking: exact match, then prefix, then substring.
  - On ties, non-planets come first, then SIMBAD `NAME` aliases.
  - `display_name` is a label, not data.
- **Tiles** (`/stars/tiles`) are octree cells over ±128 pc with brightest-first LOD, cached per
  loaded snapshot. Never return the whole catalogue (§12).
- **Tests:** db tests use the session fixture `loaded_db` (`TEST_DATABASE_URL`, wiped). API
  contract changes: run `pnpm gen:types` and commit the generated files.
