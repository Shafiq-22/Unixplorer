# CLAUDE.md — Universe Atlas: Milky Way Edition

> Operating manual for Claude Code. This file is loaded into every session, so it is kept short and imperative.
> The long-term product vision lives in `docs/spec/universe-atlas-spec.md`. Read only the section you need, on demand.
> **Current scope is the Milky Way only.** Anything extragalactic is out of scope until §13 says otherwise.

---

## 1. What we are building (this release)

A scientific web app for exploring **our galaxy** using authentic data:

1. **3D galaxy explorer**, from the Solar System out to the Galactic Centre. Stars are placed only where a distance solution exists.
2. **Object dossiers**: every value is shown with its unit, uncertainty, source and method.
3. **Space GPS**: pick two objects, inspect a route and its assumptions, choose a speed, and only then travel.
4. **Traversal simulator** comparing classical, special-relativistic (constant speed and 1 g constant acceleration), light-speed, and explicitly hypothetical FTL travel.

The flagship journey is **Earth → Sgr A\* (the Galactic Centre)**. It shows the project's whole idea in one route: a real measured distance, real relativity, a speculative comparison, and honest uncertainty.

Priority when trade-offs arise: **scientific correctness → provenance → working integration → model boundaries → reproducibility → security → performance → accessibility → visuals.**

### Data-first principle

**The data comes first, and it comes from authentic sources.** Before any app code is written, Claude Code downloads the required datasets from the official archives into `data/` in this repo. Those snapshots are the foundation for everything else:

```
official archive  →  data/raw/ (as downloaded, immutable)  →  data/processed/ (scripted)  →  database  →  API  →  UI
```

- The app runs from the local snapshot. Core features never depend on a live archive call at runtime.
- Every number shown in the UI can be traced back to a row in a file in `data/raw/`, and from there to the archive query that produced it.
- If a dataset hasn't been downloaded yet, the feature that needs it doesn't exist yet. Never stand in with typed-in, remembered or generated values.

---

## 2. Current status (Claude: keep this true)

| Area | Status |
|---|---|
| **M0 data snapshot: Gaia nearby stars** | not started |
| **M0 data snapshot: Bailer-Jones distances** | not started |
| **M0 data snapshot: SIMBAD identifiers/types** | not started |
| **M0 data snapshot: JPL Horizons bodies** | not started |
| **M0 data snapshot: landmarks** | not started |
| **M0 data snapshot: NASA Exoplanet Archive** | not started |
| **M0 manifest + checksum verification** | not started |
| Repo scaffold + CI | not started |
| Schema + migrations | not started |
| `astronomy-core` physics models | not started |
| Gaia connector (nearby stars) | not started |
| SIMBAD name resolution | not started |
| JPL Horizons (Solar System) | not started |
| Landmark set (clusters, nebulae, Sgr A\*) | not started |
| NASA Exoplanet Archive (host stars) | not started |
| Search + dossier | not started |
| 3D explorer | not started |
| Route planner | not started |
| Traversal (classical / SR / null / FTL) | not started |

Status values: `not started`, `in progress`, `working (tested)`, `partial`, `blocked: <reason>`. Update this table at the end of every task that changes it. Never mark something `working` unless its tests pass.

---

## 3. Commands

> These are planned commands. Replace them with the real ones as soon as the scaffold exists. If a command here doesn't work, fix this section.

```bash
# JS/TS (pnpm workspaces)
pnpm install
pnpm dev                       # web app
pnpm lint && pnpm typecheck
pnpm test                      # vitest
pnpm test:e2e                  # playwright

# Python (uv)
uv sync
uv run fastapi dev services/api/main.py
uv run pytest -m "not live"    # deterministic: always run
uv run pytest -m live          # hits real archives: on demand only
uv run pytest tests/scientific # physics regression suite (release-blocking)
uv run ruff check . && uv run mypy services packages

# Database
docker compose up -d db
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "<msg>"   # always review the generated file

# Data foundation (planned CLI; run in this order)
uv run atlas data fetch <dataset>      # download from the official archive into data/raw/, update manifest
uv run atlas data verify               # recompute sha256 + row counts against data/manifest.yaml
uv run atlas data build                # data/raw/ -> data/processed/*.parquet (deterministic)
uv run atlas db load                   # data/processed/ -> Postgres (idempotent upsert)
uv run atlas data status               # what is downloaded, when, from which release
```

---

## 4. Repository map (target; adapt to what exists)

```
apps/web/                    Next.js (App Router) + React Three Fiber
services/api/                FastAPI: routers, schemas, dependency injection
packages/astronomy-core/     Python: units, frames, distances, relativity (THE physics source of truth)
packages/route-planner/      Python: route geometry, travel-time orchestration
packages/universe-renderer/  TS: floating origin, LOD, instancing, picking
packages/shared-types/       TS types generated from the API's OpenAPI schema; never hand-written
data/manifest.yaml           one entry per downloaded file: source, query, release, date, sha256, rows (see §8)
data/queries/                exact ADQL / API requests used, committed as text
data/raw/<source>/<dataset>/ files exactly as the archive returned them; never edited
data/processed/              Parquet built from raw by scripts; reproducible, never hand-edited
data/CITATIONS.md            acknowledgement text each archive requires
ingestion/connectors/        gaia/, simbad/, horizons/, exoplanet_archive/: fetch code only
ingestion/pipeline/          raw → processed transforms, unit normalisation, cross-matching
ingestion/landmarks.yaml     list of landmark *names and identifiers only*; values are fetched (see §8)
database/migrations/         Alembic
tests/{unit,integration,scientific,e2e,performance}/
docs/spec/                   full long-term vision (read on demand)
docs/science/                frames.md, distances.md, relativity-models.md, ftl-scenarios.md
docs/decisions/              ADRs: NNNN-title.md
.claude/skills/              task procedures (see §12)
```

**Physics lives only in `packages/astronomy-core`.** The frontend never re-implements a formula. During animation the UI interpolates between states the backend computed, or it uses a TS port that is tested against fixtures exported from Python.

---

## 5. Hard rules (never violate)

**Data integrity**
- Never fabricate coordinates, distances, measurements, identifiers, spectra, citations, DOIs or bibcodes.
- Missing means `null` with state `unknown`. Never `0`, `NaN`-as-data, or a default value.
- RA/Dec is not a 3D position. An object without a distance solution appears in **sky view only**, never in the 3D galaxy.
- Conflicting measurements are all kept. The displayed value comes from a documented selection policy, and alternatives remain visible.
- Merges and cross-matches are reversible and record why they were made.
- Synthetic data is allowed only in test fixtures or behind an explicit `DEMO` flag.
- Every scientific value in the database must trace to a file in `data/raw/` that has a manifest entry. The loader rejects any row without that link.
- Never type a scientific value from memory or from a web page into code, config or YAML. If something can't be fetched programmatically, follow the transcription rule in §8.
- Never edit files in `data/raw/`. A re-download creates a new snapshot version; it does not overwrite the old one.

**Physics integrity**
- Every computed quantity names its model, frame, units and validity domain.
- γ, proper time and length contraction apply only to massive travellers with `0 ≤ v < c`.
- `v = c` is the null case: coordinate (light-travel) time only, with no proper time.
- `v > c` is allowed only in `hypothetical_ftl_effective`. It gives coordinate time only, and proper time is reported as "not defined by this model". Never clamp the slider to `c`.
- Visual effects not computed from a named model carry a persistent `Illustrative` or `Speculative` label.
- The galaxy's spiral-arm and disc backdrop is an **illustrative model**. It is never presented as a map of measured star positions.

**Engineering integrity**
- No control, endpoint or integration that looks finished but isn't. Unfinished features are hidden or visibly marked.
- Never claim a command, test or build succeeded without having seen its output.
- Secrets live only in `.env` (gitignored). `.env.example` contains placeholders only. Never log tokens.
- The web app never exposes shell execution, arbitrary file paths or raw database access.

---

## 6. Scientific value model

Every scientific value carries:

```
value | unit | uncertainty (lower, upper, type; may be asymmetric) | state | method | source_record_id | retrieved_at
```

`state` is one of: `measured`, `published_estimate`, `derived`, `model_predicted`, `inferred`, `illustrative`, `unknown`, `conflicting`, `invalid`, `below_detection`, `not_applicable`.

The UI renders each state distinctly. A number with no source is a bug.

Initial tables: `celestial_object`, `external_identifier`, `object_alias`, `measurement`, `position_solution`, `classification`, `scientific_source`, `publication`, `provenance_event`, `ingestion_job`, `saved_route`, `route_calculation`, `traversal_session`. The field-level design is in spec §8. Refine it through ADRs; never build one giant table.

---

## 7. Frames, distances and numerics (Milky Way specifics)

**Frames**
- Canonical storage is ICRS RA/Dec with an explicit epoch (Gaia DR3 is J2016.0) plus a separate distance solution.
- The 3D scene uses `astropy.coordinates.Galactocentric` with **pinned parameters**: record the astropy frame-defaults version (for example `v4.0`: R₀ = 8.122 kpc, z☉ = 20.8 pc) in `docs/science/frames.md` and in every `route_calculation`.
- The heliocentric view (Sun at the origin) and the galactocentric view must give identical inter-object distances. Test this.
- Solar System bodies come from JPL Horizons at a stated epoch, in the ICRF/barycentric frame, and are converted with astropy.

**Distances**
- **Never use naive `1/parallax`** when `parallax_over_error < 5` or the parallax is negative.
- The default adopted distance for Gaia stars is the Bailer-Jones et al. (2021) geometric or photogeometric estimate, which comes with asymmetric uncertainties. Verify the exact Gaia Archive table name before querying. Record which estimate was used.
- Landmarks (Sgr A\*, clusters, nebulae) use published literature distances obtained by the §8 process, never typed from memory. For Sgr A\*, store the competing published measurements as alternatives rather than a single number.
- Reality check to show users: Gaia distances are good within roughly 1–2 kpc and degrade beyond that. The 3D view of distant regions will be sparse. That is correct behaviour; do not fill it in.
- Gaia DR4 is expected around December 2026. Connectors store `data_release` so that DR3 and DR4 can coexist.

**Numerics and scale**
- SI internally, using `astropy.units`. Bare floats are not allowed in physics signatures. In TS, use branded unit types.
- Constants come from astropy: `c = 299 792 458 m/s` (exact), the AU (exact) and `pc = 648000/π AU`.
- Use float64 for all science. float32 is only for GPU buffers, after camera-relative subtraction.
- The scene spans about 10⁻⁵ pc (planetary orbits) to about 3×10⁴ pc (across the disc), roughly 10⁹ orders of scale. Use a **floating origin**, a **logarithmic depth buffer**, and positions stored as float64 on the CPU. Test that there is no visible jitter when focused on Earth, on Proxima Centauri and on Sgr A\*.

---

## 8. Data foundation (do this first: milestone M0)

### 8.1 Datasets to download

| Dataset id | Official source | What to download | Notes |
|---|---|---|---|
| `gaia_dr3_nearby` | ESA Gaia Archive (TAP, ADQL) | `gaiadr3.gaia_source` rows with `parallax > 10` mas (≤ 100 pc) and `parallax_over_error > 10`; astrometry, errors, photometry, RUWE, epoch | Bounded subset only. Never the full catalogue. Start smaller (≤ 25 pc) if the first fetch is slow |
| `gaia_dr3_distances` | Gaia Archive external table for Bailer-Jones et al. (2021) | geometric and photogeometric distances with percentiles, joined on `source_id` to the set above | Verify the table name in the archive docs before querying |
| `simbad_ids` | SIMBAD TAP | main identifiers, aliases and object types for every downloaded Gaia source and every landmark | Store the SIMBAD bibcode references SIMBAD returns |
| `horizons_bodies` | JPL Horizons API | state vectors for the Sun, 8 planets, Pluto and major moons at one fixed epoch (record it) | Store the ephemeris version string Horizons reports |
| `landmarks` | SIMBAD / VizieR, plus papers via NASA ADS | coordinates and distances for the names listed in `ingestion/landmarks.yaml` | See §8.3 |
| `exoplanets_ps` | NASA Exoplanet Archive (TAP) | `ps` table rows for hosts within the Gaia set; every solution, with `default_flag` | Keep alternative solutions |
| `galaxy_structure` | literature model tables (e.g. VizieR) | parameters for the illustrative disc/arm backdrop | Labelled `illustrative`; cite the paper |

Before writing any query, verify the endpoint, table, columns and auth requirements in the official documentation **in this session**. Do not rely on remembered column names.

### 8.2 How every download is stored

For each fetch, Claude Code must:

1. Save the exact query or request text to `data/queries/<dataset>.adql` (or `.json` for REST requests) and commit it.
2. Save the response **as returned** (VOTable, CSV or JSON) to `data/raw/<source>/<dataset>/<YYYY-MM-DD>/`.
3. Add an entry to `data/manifest.yaml`:
   ```yaml
   - dataset: gaia_dr3_nearby
     source: ESA Gaia Archive
     service_url: <the TAP endpoint actually used>
     release: Gaia DR3
     query_file: data/queries/gaia_dr3_nearby.adql
     retrieved_at: <ISO-8601 UTC timestamp>
     files:
       - path: data/raw/gaia/gaia_dr3_nearby/<date>/result.vot
         sha256: <hash>
         bytes: <size>
         rows: <count>
     license_or_credit: <text or link from the archive's terms>
     status: complete | partial (with reason)
   ```
4. Append the archive's required acknowledgement to `data/CITATIONS.md`.
5. Run `atlas data verify` and report the actual hashes and row counts.

A partial or failed download is recorded as `partial` with the reason. It is never padded to look complete.

### 8.3 Values that cannot be fetched programmatically

Some landmark values (for example a Sgr A\* distance from a specific paper) only exist in publications. For these:

- The value must come from a named paper whose **bibcode resolves in NASA ADS**, checked by a fetch saved to `data/raw/ads/`.
- Record the table, page or equation it came from, the value, the uncertainty and the unit in `data/raw/literature/<bibcode>.yaml`.
- Mark the measurement `method: transcribed` and flag it for the user to check by hand. The UI shows it as a literature value, not as catalogue data.
- Prefer a VizieR table for the same paper whenever one exists.

### 8.4 From raw files to the app

- `atlas data build` turns raw files into `data/processed/*.parquet`. It is deterministic: the same raw files always give byte-identical output, and a test checks this.
- Units are normalised in the pipeline. Original values and units are kept alongside the normalised ones.
- `atlas db load` upserts from Parquet into Postgres. Every row carries `source_record_id` pointing to its manifest file and row.
- At runtime the app reads only the database. Optional "refresh from archive" features come later, and they produce a new snapshot rather than changing rows silently.

### 8.5 Storage in git

- Commit: `manifest.yaml`, `queries/`, `CITATIONS.md`, small raw files (Horizons, landmarks, SIMBAD) and the fetch and build code.
- Large files go through **Git LFS** (set up in M0). GitHub rejects single files over 100 MB, so convert large raw tables to compressed Parquet in `processed/` and store the raw VOTable via LFS.
- Record the total `data/` size in `docs/operations/data.md` after each fetch.

### 8.6 Tests for the data layer

- `atlas data verify` runs in CI: every manifest file exists, and its hash and row count match.
- No row in the database lacks a manifest-traceable `source_record_id`.
- Spot checks: a few well-known stars (for example Proxima Centauri and Barnard's Star) are present, and their stored parallax equals the value in the raw file exactly.
- Connector code is tested against small fixtures cut from the real raw files and labelled as such. Live-archive tests are marked `@pytest.mark.live`.

---

## 9. Physics models: one code path each

| Model id | Domain | Outputs | Must NOT |
|---|---|---|---|
| `classical_constant_speed` | any v > 0 | t = D / v | be labelled relativistic |
| `sr_inertial` | massive, 0 ≤ v < c | γ, Δt, Δτ = Δt / γ | accept v ≥ c |
| `sr_constant_proper_accel` | massive; accelerate to midpoint, then decelerate, at proper acceleration a | Δt, Δτ, peak γ, v(t) | be replaced by D / v |
| `null_propagation` | v = c | light-travel time D / c | output a proper time |
| `hypothetical_ftl_effective` | v > c, labelled speculative | t_eff = D / v_eff | reuse γ, claim causality is preserved, or claim a mechanism |
| `schwarzschild_static` (later) | stationary observer, r > r_s | dτ/dt = √(1 − 2GM / (rc²)) | be applied to arbitrary environments |

All models assume **flat spacetime and static endpoints** unless stated otherwise. Galactic rotation (about 230 km/s), the gravitational potential, and stellar motion over the trip are listed as assumptions in every result, not silently ignored.

For constant proper acceleration a with a flip at the midpoint, over distance D:
`Δτ = (2c/a)·arcosh(1 + aD/(2c²))` and `Δt = (2c/a)·sinh(a·Δτ/(2c))`.

Each model returns `{model_id, model_version, inputs, outputs, assumptions[], warnings[]}`. Routes and traversals persist this object so they can be reproduced.

---

## 10. Testing

**Scientific regression tests are release-blocking.** Use these reference values (flat spacetime, g = 9.80665 m/s², Julian year):

| Case | Expected |
|---|---|
| γ(0), γ(0.6c), γ(0.8c), γ(0.99c) | 1, 1.25, 5/3, ≈ 7.0888 |
| `sr_inertial(v = c)` and `sr_inertial(v = 2c)` | raise |
| `hypothetical_ftl_effective(v = 2c)` | t = D / (2c), and no γ appears in the result |
| Proxima Centauri at 1.3012 pc: 1 g accel/decel | Δτ ≈ 3.541 yr, Δt ≈ 5.870 yr, light time ≈ 4.244 yr |
| Sgr A\* at 8.122 kpc: 1 g accel/decel | Δτ ≈ 19.79 yr, Δt ≈ 26 492 yr, light time ≈ 26 490 yr |
| Sgr A\* at 0.99c (inertial) | Δt ≈ 26 758 yr, Δτ ≈ 3 775 yr |
| Sgr A\* at 10c (FTL) | t_eff ≈ 2 649 yr, proper time "not defined" |
| Heliocentric vs galactocentric distance between two stars | equal within 1e-9 relative |
| ICRS → Galactocentric of Sgr A\* | matches astropy within tolerance |

These figures depend on the assumed distances. Tests take the distance as an input and assert against the formula. The table values document the expected magnitudes.

Other requirements:
- State the tolerance in each test (`rel=1e-9` for closed forms; looser with a reason for integrators).
- Any TS port of a formula is tested against Python-exported fixtures.
- The traversal clock is frame-rate independent: running at 16 ms and at 100 ms ticks must give the same state.
- E2E (Playwright) covers the milestone path in §11.
- Before finishing any task, run lint, typecheck, the affected tests and `tests/scientific`.

---

## 11. Milestones

**M0 — Data foundation (first, before any app code):** minimal Python project with the fetch, verify and build CLI; Git LFS; every dataset in §8.1 downloaded into `data/raw/` with manifest entries, checksums, saved queries and citations; processed Parquet built; §8.6 tests passing. Finish with a short report: datasets, row counts, sizes, releases, anything partial, and every `transcribed` value for the user to check.

**M1 — Foundation:** scaffold, CI, schema, `astronomy-core` with every §9 model and the §10 tests, and `atlas db load` populating Postgres from the M0 snapshot. No UI beyond a health page.

**M2 — Solar neighbourhood slice:** built entirely on the loaded snapshot. Search → dossier → 3D view centred on the Sun → route Sun → Proxima → travel with all model results side by side → pause, resume and cancel. E2E test.

**M3 — Solar System:** Horizons bodies at the snapshot epoch (shown in the UI), seamless zoom from planetary orbits to stellar distances (floating-origin validation), and routes starting from Earth.

**M4 — The galaxy:** galactocentric view, landmarks.yaml (Sgr A\*, clusters, nebulae), an illustrative disc and arm backdrop (labelled), sky view for objects without distances, and the flagship **Earth → Sgr A\*** route.

**M5 — Exoplanet systems:** host stars and planets from the NASA Exoplanet Archive, routes to a planet's host system, and alternative parameter solutions shown in the dossier.

**M6 — Polish:** saved routes and history, traversal replay, scenario export (JSON including model versions), accessibility pass, performance budget measured on a mid-range laptop.

Not in this release: extragalactic objects, cosmology, MAST/JWST and FITS, missions and achievements, offline mode, an AI assistant, and warp or wormhole visuals.

---

## 12. Working in this repo

**Before coding:** read the relevant spec section and any directory `CLAUDE.md`; check what already exists (extend it, don't rewrite it); verify unfamiliar APIs in official docs; write the acceptance check first.

**While coding:**
- Make small, verifiable steps and keep the app runnable after every change.
- R3F components are client-only (`'use client'`, dynamic import with SSR disabled).
- Never ship a catalogue wholesale to the browser. Serve spatial tiles by octree or HEALPix cell with LOD.
- Big decisions (a dependency, a schema change, a new service, a model choice) get an ADR. Start as a modular monolith. Add a queue or cache only when a measured need exists.

**Skills** go in `.claude/skills/<name>/SKILL.md` with `name` and `description` frontmatter, each created when its milestone starts:

| Skill | Milestone |
|---|---|
| `data-snapshot-management` (fetch → manifest → verify → build) | M0 |
| `scientific-provenance-and-validation` | M0 |
| `relativity-models` | M1 |
| `scientific-testing-and-regression` | M1 |
| `astronomical-data-engineering` | M2 |
| `galactic-frames-and-distances` | M2 |
| `webgl-galaxy-visualization` | M2 |
| `space-route-planning` | M2 |
| `accessibility-and-interface-quality` | M6 |

When a task matches a skill, read its `SKILL.md` before starting.

**Library notes** (verify before adopting): `astropy` and `astroquery` are core. `poliastro` is archived, so don't use it. For sky indexing in Postgres, prefer Q3C or pgSphere over PostGIS.

**End-of-task report:** files changed, data sources touched, tests run with their actual results, env vars required, assumptions and limitations, what is still incomplete, and an updated §2.

---

## 13. Scope expansion gate

Do not start extragalactic or cosmology work until all of these hold:
- M1–M5 are `working (tested)`.
- The physics regression suite is green in CI.
- The user explicitly approves the expansion.

Then follow spec §15 (cosmology) and §7 (NED, MAST). The `flrw_cosmology` model gets its own code path and tests, and the route planner must name which cosmological distance it uses.

---

## 14. Style

- TS: `strict`, no `any`, named exports, Zod at every trust boundary.
- Python: full type hints, mypy-clean, Pydantic at API edges, no physics in routers.
- Conventional commits: `feat:`, `fix:`, `sci:` (physics), `data:` (connectors). Keep them small.
- UI: dark, high-contrast scientific aesthetic. Every number shows its units and uncertainty. Every 3D interaction has a search or keyboard alternative. Respect reduced motion.
