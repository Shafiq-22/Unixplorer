"""`atlas db load`: data/processed/*.parquet -> Postgres, idempotently (CLAUDE.md §8.4).

Rules enforced here (schema design: docs/decisions/0002-database-schema.md):
- Only the latest *complete* manifest entry of each dataset is loaded.
- Every input row's `source_record_id` must name a file of that entry and a row inside it;
  otherwise the whole load is rejected before anything is written.
- Everything runs in one transaction with `INSERT … ON CONFLICT DO NOTHING`, so a re-run of
  the same snapshot adds nothing and a failure leaves the database unchanged.
"""

from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import unquote

import psycopg
import pyarrow.parquet as pq
import yaml

from ingestion import manifest
from ingestion.datasets import normalize_id
from ingestion.paths import Layout

LOAD_ORDER = (
    "gaia_dr3_nearby",
    "gaia_dr3_distances",
    "simbad_ids",
    "landmarks",
    "horizons_bodies",
    "exoplanets_ps",
)


class LoadError(RuntimeError):
    pass


@dataclass
class FileRef:
    id: int
    rows: int
    dataset: str


@dataclass
class LoadContext:
    layout: Layout
    conn: psycopg.Connection[Any]
    job_id: int
    entries: dict[str, manifest.Entry]
    files: dict[str, FileRef] = field(default_factory=dict)
    stats: dict[str, dict[str, int]] = field(default_factory=lambda: defaultdict(dict))

    def ref(self, source_record_id: str, dataset: str) -> tuple[int, int]:
        """(source_file_id, row) for a source_record_id, or LoadError if not manifest-backed."""
        path, sep, row_s = source_record_id.partition("#row=")
        f = self.files.get(path)
        if not sep or f is None or f.dataset != dataset:
            raise LoadError(f"{source_record_id!r} is not a file of the loaded {dataset} snapshot")
        row = int(row_s)
        if not 0 <= row < f.rows:
            raise LoadError(f"{source_record_id!r}: row outside the file's {f.rows} rows")
        return f.id, row


def psycopg_url(url: str) -> str:
    return re.sub(r"^postgresql\+psycopg://", "postgresql://", url)


def run_load(layout: Layout, url: str, *, command: str = "atlas db load") -> dict[str, Any]:
    entries = manifest.load(layout)
    latest = {}
    for ds in LOAD_ORDER:
        e = manifest.latest_complete(entries, ds)
        if e is None:
            raise LoadError(f"no complete snapshot of {ds} in data/manifest.yaml")
        if not (layout.processed / f"{ds}.parquet").exists():
            raise LoadError(f"data/processed/{ds}.parquet missing: run `atlas data build` first")
        latest[ds] = e
    _check_build_matches_manifest(layout, latest)

    with psycopg.connect(psycopg_url(url), autocommit=True) as jconn:
        job_id = jconn.execute(
            "INSERT INTO ingestion_job (command, status, snapshot, stats) "
            "VALUES (%s, 'running', %s, '{}') RETURNING id",
            (command, json.dumps({d: e.retrieved_at for d, e in latest.items()})),
        ).fetchone()[0]  # type: ignore[index]
        try:
            with psycopg.connect(psycopg_url(url)) as conn, conn.transaction():
                ctx = LoadContext(layout, conn, job_id, latest)
                _register_sources(ctx)
                _load_gaia(ctx)
                _load_simbad_ids(ctx)
                _load_landmarks(ctx)
                _load_horizons(ctx)
                _load_exoplanets(ctx)
                _derive_positions(ctx)
                stats = {k: dict(v) for k, v in ctx.stats.items()}
        except Exception as exc:
            jconn.execute(
                "UPDATE ingestion_job SET status='failed', finished_at=now(), error=%s WHERE id=%s",
                (f"{type(exc).__name__}: {exc}"[:4000], job_id),
            )
            raise
        jconn.execute(
            "UPDATE ingestion_job SET status='complete', finished_at=now(), stats=%s WHERE id=%s",
            (json.dumps(stats), job_id),
        )
    return {"job_id": job_id, "stats": stats}


def _check_build_matches_manifest(layout: Layout, latest: dict[str, manifest.Entry]) -> None:
    """The processed Parquet must have been built from exactly these manifest files."""
    for ds, e in latest.items():
        md = pq.read_schema(layout.processed / f"{ds}.parquet").metadata or {}
        built = json.loads(md.get(b"atlas.inputs", b"[]"))
        expected = [{"path": f.path, "sha256": f.sha256} for f in e.files if f.role == "data"]
        if built != expected:
            raise LoadError(f"{ds}.parquet was not built from the current manifest; rebuild it")


# ------------------------------------------------------------------------------ helpers


def _register_sources(ctx: LoadContext) -> None:
    for ds, e in ctx.entries.items():
        src_id = ctx.conn.execute(
            """INSERT INTO scientific_source
                   (dataset, source, service_url, release, query_file, retrieved_at,
                    license_or_credit)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (dataset, retrieved_at) DO UPDATE SET dataset = EXCLUDED.dataset
               RETURNING id""",
            (
                ds,
                e.source,
                e.service_url,
                e.release,
                e.query_file,
                e.retrieved_at,
                e.license_or_credit,
            ),
        ).fetchone()[0]  # type: ignore[index]
        for f in e.files:
            if f.role != "data":
                continue
            fid = ctx.conn.execute(
                """INSERT INTO source_file (scientific_source_id, path, sha256, bytes, rows)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (path) DO UPDATE SET path = EXCLUDED.path
                   RETURNING id, sha256""",
                (src_id, f.path, f.sha256, f.bytes, f.rows),
            ).fetchone()
            assert fid is not None
            if fid[1] != f.sha256:
                raise LoadError(f"{f.path} is in the database with a different sha256")
            ctx.files[f.path] = FileRef(fid[0], f.rows, ds)


def _rows(ctx: LoadContext, dataset: str, columns: Sequence[str]) -> Iterator[dict[str, Any]]:
    table = pq.read_table(
        ctx.layout.processed / f"{dataset}.parquet", columns=[*columns, "source_record_id"]
    )
    for batch in table.to_batches(max_chunksize=50_000):
        yield from batch.to_pylist()


def _units(ctx: LoadContext, dataset: str) -> dict[str, str]:
    schema = pq.read_schema(ctx.layout.processed / f"{dataset}.parquet")
    return {f.name: (f.metadata or {}).get(b"unit", b"").decode() for f in schema}


def _num(v: Any) -> float | None:
    if v is None:
        return None
    x = float(v)
    return None if math.isnan(x) else x


def _copy(
    ctx: LoadContext, table: str, columns: Sequence[str], rows: Iterable[Sequence[Any]]
) -> int:
    n = 0
    with (
        ctx.conn.cursor() as cur,
        cur.copy(f"COPY {table} ({', '.join(columns)}) FROM STDIN") as cp,
    ):
        for r in rows:
            cp.write_row(r)
            n += 1
    return n


def _exec(ctx: LoadContext, sql: str, params: Sequence[Any] = ()) -> int:
    with ctx.conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.rowcount


STAGE_DDL = {
    "stage_object": "natural_key text, object_type text, primary_name text",
    "stage_ident": (
        "natural_key text, catalogue text, identifier text, file_id int, row int, rid text, "
        "event_id bigint"
    ),
    "stage_alias": "natural_key text, alias text, file_id int, row int, rid text, event_id bigint",
    "stage_class": (
        "natural_key text, scheme text, value text, file_id int, row int, rid text, event_id bigint"
    ),
    "stage_measure": (
        "natural_key text, quantity text, value float8, unit text, lo float8, hi float8, "
        "utype text, state text, method text, solution_key text, is_default bool, bibcode text, "
        "file_id int, row int, rid text, retrieved_at timestamptz"
    ),
    "stage_position": (
        "natural_key text, kind text, frame text, epoch text, ra float8, dec float8, "
        "ra_err float8, dec_err float8, pmethod text, pstate text, dist float8, dist_lo float8, "
        "dist_hi float8, dist_interval text, dist_method text, dist_state text, dist_file_id int, "
        "dist_row int, dist_rid text, x float8, y float8, z float8, vx float8, vy float8, "
        "vz float8, bibcode text, file_id int, row int, rid text"
    ),
    "stage_pub": "bibcode text, citation text",
}


def _stage(ctx: LoadContext, name: str) -> None:
    _exec(ctx, f"DROP TABLE IF EXISTS {name}")
    _exec(ctx, f"CREATE TEMP TABLE {name} ({STAGE_DDL[name]}) ON COMMIT DROP")


def _flush(ctx: LoadContext, dataset: str) -> None:
    """Move every stage table into the real tables. Joins resolve objects by natural_key."""
    s = ctx.stats[dataset]
    s["objects"] = s.get("objects", 0) + _exec(
        ctx,
        """INSERT INTO celestial_object (natural_key, object_type, primary_name, created_by_job_id)
           SELECT DISTINCT ON (natural_key) natural_key, object_type, primary_name, %s
           FROM stage_object ORDER BY natural_key
           ON CONFLICT (natural_key) DO NOTHING""",
        (ctx.job_id,),
    )
    _exec(
        ctx,
        """INSERT INTO publication (bibcode, citation)
           SELECT DISTINCT ON (bibcode) bibcode, citation FROM stage_pub ORDER BY bibcode
           ON CONFLICT (bibcode) DO NOTHING""",
    )
    s["identifiers"] = s.get("identifiers", 0) + _exec(
        ctx,
        """INSERT INTO external_identifier (object_id, catalogue, identifier, source_file_id,
                                            source_row, source_record_id, provenance_event_id)
           SELECT o.id, st.catalogue, st.identifier, st.file_id, st.row, st.rid, st.event_id
           FROM stage_ident st JOIN celestial_object o ON o.natural_key = st.natural_key
           ON CONFLICT (catalogue, identifier) DO NOTHING""",
    )
    s["aliases"] = s.get("aliases", 0) + _exec(
        ctx,
        """INSERT INTO object_alias (object_id, alias, alias_normalized, catalogue, source_file_id,
                                     source_row, source_record_id, provenance_event_id)
           SELECT o.id, st.alias, lower(regexp_replace(btrim(st.alias), '\\s+', ' ', 'g')),
                  'simbad', st.file_id, st.row, st.rid, st.event_id
           FROM stage_alias st JOIN celestial_object o ON o.natural_key = st.natural_key
           ON CONFLICT (object_id, alias) DO NOTHING""",
    )
    s["classifications"] = s.get("classifications", 0) + _exec(
        ctx,
        """INSERT INTO classification (object_id, scheme, value, source_file_id, source_row,
                                       source_record_id, provenance_event_id)
           SELECT o.id, st.scheme, st.value, st.file_id, st.row, st.rid, st.event_id
           FROM stage_class st JOIN celestial_object o ON o.natural_key = st.natural_key
           ON CONFLICT (object_id, scheme, value) DO NOTHING""",
    )
    s["measurements"] = s.get("measurements", 0) + _exec(
        ctx,
        """INSERT INTO measurement (object_id, quantity, value, unit, uncertainty_lower,
                                    uncertainty_upper, uncertainty_type, state, method,
                                    solution_key, is_default, publication_id, source_file_id,
                                    source_row, source_record_id, retrieved_at)
           SELECT o.id, st.quantity, st.value, st.unit, st.lo, st.hi, st.utype, st.state,
                  st.method, st.solution_key, st.is_default, p.id, st.file_id, st.row, st.rid,
                  st.retrieved_at
           FROM stage_measure st
           JOIN celestial_object o ON o.natural_key = st.natural_key
           LEFT JOIN publication p ON p.bibcode = st.bibcode
           ON CONFLICT (object_id, quantity, source_file_id, source_row) DO NOTHING""",
    )
    s["positions"] = s.get("positions", 0) + _exec(
        ctx,
        """INSERT INTO position_solution (object_id, kind, frame, epoch, ra_deg, dec_deg,
               ra_error_mas, dec_error_mas, position_method, position_state, distance_pc,
               distance_lower_pc, distance_upper_pc, distance_interval, distance_method,
               distance_state, distance_source_file_id, distance_source_row,
               distance_source_record_id, x_km, y_km, z_km, vx_km_s, vy_km_s, vz_km_s,
               is_adopted, publication_id, source_file_id, source_row, source_record_id)
           SELECT o.id, st.kind, st.frame, st.epoch, st.ra, st.dec, st.ra_err, st.dec_err,
                  st.pmethod, st.pstate, st.dist, st.dist_lo, st.dist_hi, st.dist_interval,
                  st.dist_method, st.dist_state, st.dist_file_id, st.dist_row, st.dist_rid,
                  st.x, st.y, st.z, st.vx, st.vy, st.vz, true, p.id, st.file_id, st.row, st.rid
           FROM stage_position st
           JOIN celestial_object o ON o.natural_key = st.natural_key
           LEFT JOIN publication p ON p.bibcode = st.bibcode
           ON CONFLICT (object_id, kind, source_file_id, source_row) DO NOTHING""",
    )


def _begin(ctx: LoadContext) -> None:
    for name in STAGE_DDL:
        _stage(ctx, name)


def _event(
    ctx: LoadContext, event_type: str, dataset: str, reason: str, detail: dict[str, Any]
) -> int:
    row = ctx.conn.execute(
        """INSERT INTO provenance_event (ingestion_job_id, event_type, dataset, reason, detail)
           VALUES (%s, %s, %s, %s, %s)
           ON CONFLICT (event_type, dataset, reason) DO UPDATE SET detail = EXCLUDED.detail
           RETURNING id""",
        (ctx.job_id, event_type, dataset, reason, json.dumps(detail)),
    ).fetchone()
    assert row is not None
    return int(row[0])


def _measure_row(
    nk: str,
    quantity: str,
    value: Any,
    unit: str,
    *,
    lo: float | None = None,
    hi: float | None = None,
    utype: str | None = None,
    state: str,
    method: str,
    ref: tuple[int, int],
    rid: str,
    retrieved_at: str,
    solution_key: str | None = None,
    is_default: bool | None = None,
    bibcode: str | None = None,
) -> tuple[Any, ...]:
    v = _num(value)
    if v is None:
        state, lo, hi, utype = "unknown", None, None, None
    return (
        nk,
        quantity,
        v,
        unit,
        lo,
        hi,
        utype,
        state,
        method,
        solution_key,
        is_default,
        bibcode,
        ref[0],
        ref[1],
        rid,
        retrieved_at,
    )


MEASURE_COLS = (
    "natural_key",
    "quantity",
    "value",
    "unit",
    "lo",
    "hi",
    "utype",
    "state",
    "method",
    "solution_key",
    "is_default",
    "bibcode",
    "file_id",
    "row",
    "rid",
    "retrieved_at",
)
POSITION_COLS = tuple(c.split()[0] for c in STAGE_DDL["stage_position"].split(", "))


# --------------------------------------------------------------------------------- Gaia

GAIA_MEASURES = (
    # (quantity, error column, state, method)
    ("parallax", "parallax_error", "measured", "gaia_dr3_astrometry"),
    ("pmra", "pmra_error", "measured", "gaia_dr3_astrometry"),
    ("pmdec", "pmdec_error", "measured", "gaia_dr3_astrometry"),
    ("radial_velocity", "radial_velocity_error", "measured", "gaia_dr3_rvs"),
    ("phot_g_mean_mag", None, "measured", "gaia_dr3_photometry"),
    ("phot_bp_mean_mag", None, "measured", "gaia_dr3_photometry"),
    ("phot_rp_mean_mag", None, "measured", "gaia_dr3_photometry"),
    ("bp_rp", None, "derived", "gaia_dr3_photometry"),
    ("ruwe", None, "derived", "gaia_dr3_astrometric_quality"),
)
BJ = (("geometric", "geo"), ("photogeometric", "photogeo"))


def _load_gaia(ctx: LoadContext) -> None:
    _begin(ctx)
    ds, dds = "gaia_dr3_nearby", "gaia_dr3_distances"
    units, dunits = _units(ctx, ds), _units(ctx, dds)
    t_ret, d_ret = ctx.entries[ds].retrieved_at, ctx.entries[dds].retrieved_at

    # Distances first, keyed by source_id, so each position can carry its adopted distance.
    dist: dict[int, dict[str, Any]] = {}
    dcols = ["source_id", "flag"] + [f"r_{p}_{k}" for _, k in BJ for p in ("med", "lo", "hi")]
    measures: list[tuple[Any, ...]] = []
    classes: list[tuple[Any, ...]] = []
    for r in _rows(ctx, dds, dcols):
        ref = ctx.ref(r["source_record_id"], dds)
        nk = f"gaia_dr3:{r['source_id']}"
        dist[int(r["source_id"])] = {**r, "_ref": ref}
        for name, k in BJ:
            measures.append(
                _measure_row(
                    nk,
                    f"distance_bj_{name}",
                    r[f"r_med_{k}"],
                    dunits[f"r_med_{k}"],
                    lo=_num(r[f"r_lo_{k}"]),
                    hi=_num(r[f"r_hi_{k}"]),
                    utype="interval_bounds_p16_p84",
                    state="published_estimate",
                    method=f"bailer_jones_2021_{name}",
                    ref=ref,
                    rid=r["source_record_id"],
                    retrieved_at=d_ret,
                )
            )
        if r["flag"] is not None:
            classes.append((nk, "bj2021_flag", str(r["flag"]), *ref, r["source_record_id"], None))

    objects, idents, positions = [], [], []
    cols = [
        "source_id",
        "designation",
        "ref_epoch",
        "ra",
        "ra_error",
        "dec",
        "dec_error",
        *[q for q, *_ in GAIA_MEASURES],
        *[e for _, e, *_ in GAIA_MEASURES if e],
    ]
    for r in _rows(ctx, ds, cols):
        ref = ctx.ref(r["source_record_id"], ds)
        rid = r["source_record_id"]
        sid = int(r["source_id"])
        nk = f"gaia_dr3:{sid}"
        objects.append((nk, "star", r["designation"]))
        idents.append((nk, "gaia_dr3", str(sid), *ref, rid, None))
        for q, err, state, method in GAIA_MEASURES:
            e = _num(r[err]) if err else None
            measures.append(
                _measure_row(
                    nk,
                    q,
                    r[q],
                    units[q],
                    lo=e,
                    hi=e,
                    utype="symmetric_1sigma" if e is not None else None,
                    state=state,
                    method=method,
                    ref=ref,
                    rid=rid,
                    retrieved_at=t_ret,
                )
            )
        d = dist.get(sid)
        geo = _num(d["r_med_geo"]) if d else None
        positions.append(
            (
                nk,
                "sky",
                "ICRS",
                f"J{r['ref_epoch']}",
                _num(r["ra"]),
                _num(r["dec"]),
                _num(r["ra_error"]),
                _num(r["dec_error"]),
                "gaia_dr3_astrometry",
                "measured",
                geo,
                _num(d["r_lo_geo"]) if geo is not None and d else None,
                _num(d["r_hi_geo"]) if geo is not None and d else None,
                "p16_p84" if geo is not None else None,
                "bailer_jones_2021_geometric" if geo is not None else None,
                "published_estimate" if geo is not None else "unknown",
                d["_ref"][0] if geo is not None and d else None,
                d["_ref"][1] if geo is not None and d else None,
                d["source_record_id"] if geo is not None and d else None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                *ref,
                rid,
            )
        )
    _copy(ctx, "stage_object", ("natural_key", "object_type", "primary_name"), objects)
    _copy(
        ctx,
        "stage_ident",
        ("natural_key", "catalogue", "identifier", "file_id", "row", "rid", "event_id"),
        idents,
    )
    _copy(ctx, "stage_measure", MEASURE_COLS, measures)
    _copy(
        ctx,
        "stage_class",
        ("natural_key", "scheme", "value", "file_id", "row", "rid", "event_id"),
        classes,
    )
    _copy(ctx, "stage_position", POSITION_COLS, positions)
    _flush(ctx, ds)
    ctx.stats[ds]["input_rows"] = len(objects)
    ctx.stats[dds]["input_rows"] = len(dist)


# ------------------------------------------------------------------------------- SIMBAD

CROSSMATCH_REASON = "SIMBAD identifier equals 'Gaia DR3 <source_id>' (exact, from SIMBAD ident)"


def _load_simbad_ids(ctx: LoadContext) -> None:
    _begin(ctx)
    ds = "simbad_ids"
    rows = list(_rows(ctx, ds, ["query_id", "oid", "main_id", "otype", "alias"]))
    gaia_to_oids: dict[str, set[int]] = defaultdict(set)
    oid_to_gaia: dict[int, set[str]] = defaultdict(set)
    for r in rows:
        gaia_to_oids[r["query_id"]].add(int(r["oid"]))
        oid_to_gaia[int(r["oid"])].add(r["query_id"])
    ambiguous_gaia = sorted(g for g, o in gaia_to_oids.items() if len(o) > 1)
    ambiguous_oid = sorted(o for o, g in oid_to_gaia.items() if len(g) > 1)
    skip = set(ambiguous_gaia) | {g for o in ambiguous_oid for g in oid_to_gaia[o]}
    event = _event(
        ctx,
        "crossmatch",
        ds,
        CROSSMATCH_REASON,
        {
            "method": "exact identifier match in SIMBAD's ident table",
            "skipped_ambiguous_gaia_ids": ambiguous_gaia[:1000],
            "skipped_ambiguous_simbad_oids": ambiguous_oid[:1000],
            "skipped_count": len(skip),
            "reverse": "DELETE rows WHERE provenance_event_id = this id",
        },
    )
    idents, aliases, classes = [], [], []
    seen: set[str] = set()
    for r in rows:
        if r["query_id"] in skip:
            continue
        nk = f"gaia_dr3:{r['query_id'].removeprefix('Gaia DR3 ')}"
        ref = ctx.ref(r["source_record_id"], ds)
        rid = r["source_record_id"]
        if r["query_id"] not in seen:
            seen.add(r["query_id"])
            idents.append((nk, "simbad_oid", str(r["oid"]), *ref, rid, event))
            idents.append((nk, "simbad_main_id", r["main_id"], *ref, rid, event))
            if r["otype"]:
                classes.append((nk, "simbad_otype", r["otype"], *ref, rid, event))
        aliases.append((nk, r["alias"], *ref, rid, event))
    _copy(
        ctx,
        "stage_ident",
        ("natural_key", "catalogue", "identifier", "file_id", "row", "rid", "event_id"),
        idents,
    )
    _copy(
        ctx, "stage_alias", ("natural_key", "alias", "file_id", "row", "rid", "event_id"), aliases
    )
    _copy(
        ctx,
        "stage_class",
        ("natural_key", "scheme", "value", "file_id", "row", "rid", "event_id"),
        classes,
    )
    _flush(ctx, ds)
    ctx.stats[ds].update(
        input_rows=len(rows), matched_gaia_sources=len(seen), skipped_ambiguous=len(skip)
    )


def _load_landmarks(ctx: LoadContext) -> None:
    _begin(ctx)
    ds = "landmarks"
    spec = yaml.safe_load(ctx.layout.landmarks.read_text(encoding="utf-8"))["landmarks"]
    by_id = {normalize_id(str(lm["simbad_id"])): lm for lm in spec}
    rows = list(
        _rows(
            ctx,
            ds,
            [
                "query_id",
                "oid",
                "main_id",
                "otype",
                "ra",
                "dec",
                "coo_err_maj",
                "coo_err_min",
                "coo_bibcode",
                "alias",
            ],
        )
    )
    units = _units(ctx, ds)
    ret = ctx.entries[ds].retrieved_at
    # Reuse an object that already carries this SIMBAD oid (e.g. a Gaia star), else a new key.
    oids = sorted({int(r["oid"]) for r in rows})
    existing = dict(
        ctx.conn.execute(
            """SELECT e.identifier::bigint, o.natural_key FROM external_identifier e
           JOIN celestial_object o ON o.id = e.object_id
           WHERE e.catalogue = 'simbad_oid' AND e.identifier = ANY(%s)""",
            ([str(o) for o in oids],),
        ).fetchall()
    )
    objects, idents, aliases, classes, measures, positions, pubs = [], [], [], [], [], [], []
    done: set[int] = set()
    for r in rows:
        oid = int(r["oid"])
        lm = by_id.get(normalize_id(r["query_id"]))
        if lm is None:
            raise LoadError(f"landmark row for {r['query_id']!r} matches no landmarks.yaml entry")
        nk = existing.get(oid, f"simbad:{oid}")
        ref = ctx.ref(r["source_record_id"], ds)
        rid = r["source_record_id"]
        aliases.append((nk, r["alias"], *ref, rid, None))
        if oid in done:
            continue
        done.add(oid)
        objects.append((nk, lm["kind"], lm["label"]))
        idents.append((nk, "simbad_oid", str(oid), *ref, rid, None))
        idents.append((nk, "simbad_main_id", r["main_id"], *ref, rid, None))
        idents.append((nk, "atlas_landmark", lm["key"], *ref, rid, None))
        if r["otype"]:
            classes.append((nk, "simbad_otype", r["otype"], *ref, rid, None))
        if r["coo_bibcode"]:
            pubs.append((r["coo_bibcode"], None))
        for q in ("coo_err_maj", "coo_err_min"):
            measures.append(
                _measure_row(
                    nk,
                    f"simbad_{q}",
                    r[q],
                    units[q],
                    state="published_estimate",
                    method="simbad_coordinates",
                    ref=ref,
                    rid=rid,
                    retrieved_at=ret,
                    bibcode=r["coo_bibcode"] or None,
                )
            )
        positions.append(
            (
                nk,
                "sky",
                "ICRS (SIMBAD basic.ra/dec, UCD pos.eq)",
                "not stated by SIMBAD TAP_SCHEMA",
                _num(r["ra"]),
                _num(r["dec"]),
                None,
                None,
                "simbad_coordinates",
                "published_estimate",
                None,
                None,
                None,
                None,
                None,
                "unknown",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                r["coo_bibcode"] or None,
                *ref,
                rid,
            )
        )
    _copy(ctx, "stage_object", ("natural_key", "object_type", "primary_name"), objects)
    _copy(ctx, "stage_pub", ("bibcode", "citation"), pubs)
    _copy(
        ctx,
        "stage_ident",
        ("natural_key", "catalogue", "identifier", "file_id", "row", "rid", "event_id"),
        idents,
    )
    _copy(
        ctx, "stage_alias", ("natural_key", "alias", "file_id", "row", "rid", "event_id"), aliases
    )
    _copy(
        ctx,
        "stage_class",
        ("natural_key", "scheme", "value", "file_id", "row", "rid", "event_id"),
        classes,
    )
    _copy(ctx, "stage_measure", MEASURE_COLS, measures)
    _copy(ctx, "stage_position", POSITION_COLS, positions)
    _flush(ctx, ds)
    ctx.stats[ds]["input_rows"] = len(rows)


# ------------------------------------------------------------------------------ Horizons


def _load_horizons(ctx: LoadContext) -> None:
    _begin(ctx)
    ds = "horizons_bodies"
    objects, idents, positions = [], [], []
    for r in _rows(ctx, ds, ["target", "JDTDB", "X", "Y", "Z", "VX", "VY", "VZ"]):
        ref = ctx.ref(r["source_record_id"], ds)
        nk = f"horizons:{r['target']}"
        objects.append((nk, "solar_system_body", r["target"]))
        idents.append((nk, "jpl_horizons_target", r["target"], *ref, r["source_record_id"], None))
        positions.append(
            (
                nk,
                "state_vector",
                "ICRF axes, Solar System barycentre (Horizons CENTER=500@0, REF_PLANE=FRAME)",
                f"JD {r['JDTDB']} TDB",
                None,
                None,
                None,
                None,
                "jpl_horizons_ephemeris",
                "model_predicted",
                None,
                None,
                None,
                None,
                None,
                "not_applicable",
                None,
                None,
                None,
                _num(r["X"]),
                _num(r["Y"]),
                _num(r["Z"]),
                _num(r["VX"]),
                _num(r["VY"]),
                _num(r["VZ"]),
                None,
                *ref,
                r["source_record_id"],
            )
        )
    _copy(ctx, "stage_object", ("natural_key", "object_type", "primary_name"), objects)
    _copy(
        ctx,
        "stage_ident",
        ("natural_key", "catalogue", "identifier", "file_id", "row", "rid", "event_id"),
        idents,
    )
    _copy(ctx, "stage_position", POSITION_COLS, positions)
    _flush(ctx, ds)
    ctx.stats[ds]["input_rows"] = len(objects)


# ---------------------------------------------------------------------------- Exoplanets

PS_QUANTITIES = ("pl_orbper", "pl_orbsmax", "pl_rade", "pl_bmasse", "pl_orbeccen", "pl_eqt")
_REFSTR = re.compile(r"refstr=([^\s>]+)")
_BIBCODE = re.compile(r"/abs/([^/\"'\s>]+)")
_ANCHOR_TEXT = re.compile(r">([^<]*)</a>")


def parse_reference(html: str | None) -> tuple[str | None, str | None, str | None]:
    """(refstr, bibcode, citation text) from the archive's own reference link, if present."""
    if not html:
        return None, None, None
    refstr = _REFSTR.search(html)
    bib = _BIBCODE.search(html)
    text = _ANCHOR_TEXT.search(html)
    return (
        refstr.group(1) if refstr else None,
        unquote(bib.group(1)) if bib else None,
        text.group(1).strip() if text else None,
    )


def _load_exoplanets(ctx: LoadContext) -> None:
    _begin(ctx)
    ds = "exoplanets_ps"
    units = _units(ctx, ds)
    ret = ctx.entries[ds].retrieved_at
    cols = ["pl_name", "hostname", "gaia_dr3_id", "default_flag", "pl_refname"]
    for q in PS_QUANTITIES:
        cols += [q, f"{q}err1", f"{q}err2", f"{q}lim"]
    objects, idents, measures, pubs = [], [], [], []
    hosts: dict[str, str] = {}
    seen: set[str] = set()
    for r in _rows(ctx, ds, cols):
        ref = ctx.ref(r["source_record_id"], ds)
        rid = r["source_record_id"]
        nk = f"exoplanet_archive:{r['pl_name']}"
        if r["pl_name"] not in seen:
            seen.add(r["pl_name"])
            objects.append((nk, "exoplanet", r["pl_name"]))
            idents.append((nk, "exoplanet_archive_pl_name", r["pl_name"], *ref, rid, None))
        if r["gaia_dr3_id"]:
            hosts.setdefault(nk, r["gaia_dr3_id"])
        refstr, bibcode, citation = parse_reference(r["pl_refname"])
        if bibcode:
            pubs.append((bibcode, citation))
        for q in PS_QUANTITIES:
            lim = r[f"{q}lim"]
            e_hi, e_lo = _num(r[f"{q}err1"]), _num(r[f"{q}err2"])
            if lim == 1:
                utype, lo, hi = "upper_limit", None, None
            elif lim == -1:
                utype, lo, hi = "lower_limit", None, None
            elif e_hi is not None or e_lo is not None:
                utype = "asymmetric_offsets"
                lo = abs(e_lo) if e_lo is not None else None
                hi = abs(e_hi) if e_hi is not None else None
            else:
                utype, lo, hi = None, None, None
            measures.append(
                _measure_row(
                    nk,
                    q,
                    r[q],
                    units[q],
                    lo=lo,
                    hi=hi,
                    utype=utype,
                    state="published_estimate",
                    method="nasa_exoplanet_archive_ps",
                    ref=ref,
                    rid=rid,
                    retrieved_at=ret,
                    solution_key=refstr,
                    is_default=bool(r["default_flag"] == 1),
                    bibcode=bibcode,
                )
            )
    _copy(ctx, "stage_object", ("natural_key", "object_type", "primary_name"), objects)
    _copy(ctx, "stage_pub", ("bibcode", "citation"), pubs)
    _copy(
        ctx,
        "stage_ident",
        ("natural_key", "catalogue", "identifier", "file_id", "row", "rid", "event_id"),
        idents,
    )
    _copy(ctx, "stage_measure", MEASURE_COLS, measures)
    _flush(ctx, ds)
    linked = 0
    for nk, gaia_id in hosts.items():
        sid = gaia_id.removeprefix("Gaia DR3 ").strip()
        linked += _exec(
            ctx,
            """UPDATE celestial_object p SET parent_object_id = h.id, parent_link_reason = %s
               FROM celestial_object h
               WHERE p.natural_key = %s AND h.natural_key = %s AND p.parent_object_id IS NULL""",
            (f"NASA Exoplanet Archive gaia_dr3_id = '{gaia_id}'", nk, f"gaia_dr3:{sid}"),
        )
    ctx.stats[ds].update(planets=len(seen), hosts_linked_to_gaia=linked)


# ------------------------------------------------------------------- derived positions


def _derive_positions(ctx: LoadContext) -> None:
    """Fill bary_x/y/z_pc + bary_xyz for rows that have a 3D position and none derived yet.

    Physics stays in astronomy_core (CLAUDE.md §4): this only moves numbers in and out.
    Sky-only rows (no distance) are never given a 3D position (§5).
    """
    import astropy.units as u
    import numpy as np

    from astronomy_core.frames import CARTESIAN_METHOD, icrs_barycentric_xyz, state_vector_xyz

    sky = ctx.conn.execute(
        """SELECT id, ra_deg, dec_deg, distance_pc FROM position_solution
           WHERE kind = 'sky' AND distance_pc IS NOT NULL AND bary_x_pc IS NULL"""
    ).fetchall()
    vec = ctx.conn.execute(
        """SELECT id, x_km, y_km, z_km FROM position_solution
           WHERE kind = 'state_vector' AND x_km IS NOT NULL AND bary_x_pc IS NULL"""
    ).fetchall()
    out: list[tuple[int, float, float, float]] = []
    if sky:
        a = np.array([r[1:] for r in sky], dtype=np.float64)
        x, y, z = icrs_barycentric_xyz(a[:, 0] * u.deg, a[:, 1] * u.deg, a[:, 2] * u.pc)
        out += [
            (int(r[0]), float(xi), float(yi), float(zi))
            for r, xi, yi, zi in zip(
                sky, x.to_value(u.pc), y.to_value(u.pc), z.to_value(u.pc), strict=True
            )
        ]
    if vec:
        a = np.array([r[1:] for r in vec], dtype=np.float64)
        x, y, z = state_vector_xyz(a[:, 0] * u.km, a[:, 1] * u.km, a[:, 2] * u.km)
        out += [
            (int(r[0]), float(xi), float(yi), float(zi))
            for r, xi, yi, zi in zip(
                vec, x.to_value(u.pc), y.to_value(u.pc), z.to_value(u.pc), strict=True
            )
        ]
    _exec(ctx, "DROP TABLE IF EXISTS stage_xyz")
    _exec(
        ctx, "CREATE TEMP TABLE stage_xyz (id bigint, x float8, y float8, z float8) ON COMMIT DROP"
    )
    _copy(ctx, "stage_xyz", ("id", "x", "y", "z"), out)
    ctx.stats["derived"]["positions"] = _exec(
        ctx,
        """UPDATE position_solution p
           SET bary_x_pc = s.x, bary_y_pc = s.y, bary_z_pc = s.z,
               bary_xyz = cube(ARRAY[s.x, s.y, s.z]), derived_method = %s
           FROM stage_xyz s WHERE p.id = s.id""",
        (CARTESIAN_METHOD,),
    )
