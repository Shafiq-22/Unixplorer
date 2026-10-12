---
name: data-snapshot-management
description: Fetch, record, verify and build the archive data snapshot (data/raw → manifest → data/processed). Use for any task that downloads, re-downloads, checks or transforms datasets.
---

# Data snapshot management

1. Check state: `uv run atlas data status` and `uv run atlas data verify`.
2. Fetch in dependency order (see `docs/operations/data.md`): `uv run atlas data fetch <id>`.
   - The query text lives in `data/queries/`. Change a query there, never inline.
   - Fetch runs a `TAP_SCHEMA` pre-flight. If it reports missing columns, fix the query and the
     `required_columns` entry in `ingestion/datasets.py` to match the archive's documentation.
     Never guess.
   - A failure is recorded as `partial: <reason>`. Leave it recorded. A later fetch adds a new
     entry; it does not replace the old one.
3. `uv run atlas data verify`: it must report 0 problems. Paste the real hashes and row counts into
   your report.
4. `uv run atlas data build`, then `uv run pytest -m "not live"`. The snapshot spot checks
   (Proxima, Barnard) must pass rather than skip once Gaia and SIMBAD are built.
5. Update `data/CITATIONS.md` (verbatim archive text) and the size log in
   `docs/operations/data.md`.
6. Never edit anything under `data/raw/` and never hand-edit `data/manifest.yaml`.
