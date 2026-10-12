"""Registry of the M0 datasets (CLAUDE.md §8.1) and how each one is fetched."""

from __future__ import annotations

import io
import json
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

import requests
import yaml

from ingestion import manifest
from ingestion.connectors import horizons
from ingestion.connectors.tap import TapClient, TapError, adql_in_list
from ingestion.paths import Layout

GAIA_TAP = "https://gea.esac.esa.int/tap-server/tap"
SIMBAD_TAP = "https://simbad.cds.unistra.fr/simbad/sim-tap"
EXOPLANET_TAP = "https://exoplanetarchive.ipac.caltech.edu/TAP"


@dataclass
class FetchContext:
    layout: Layout
    dataset: Dataset
    snapshot_dir: Path
    session: requests.Session
    batch_size: int = 1000
    files: list[manifest.FileRecord] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    partial_reason: str | None = None
    release_detail: str | None = None
    resume_job_url: str | None = None

    def save(self, name: str, content: bytes, role: str = "data") -> Path:
        path = self.snapshot_dir / name
        if path.exists():
            raise FileExistsError(f"refusing to overwrite raw file {path}")
        path.write_bytes(content)
        self.files.append(manifest.record_file(self.layout, path, role))
        return path

    def query_text(self) -> str:
        return (self.layout.queries / self.dataset.query_file).read_text(encoding="utf-8")


Fetcher = Callable[[FetchContext], None]


@dataclass(frozen=True)
class Dataset:
    id: str
    source: str
    source_dir: str
    service_url: str
    release: str
    query_file: str
    fetch: Fetcher | None
    required_columns: dict[str, tuple[str, ...]] = field(default_factory=dict)
    depends_on: tuple[str, ...] = ()
    blocked_reason: str | None = None


def strip_comments(adql: str) -> str:
    """Drop whole-line `--` comments; the committed file keeps them, the service gets clean ADQL."""
    return "\n".join(ln for ln in adql.splitlines() if not ln.lstrip().startswith("--")).strip()


def _schema_checks(ctx: FetchContext, tap: TapClient) -> None:
    for table, cols in ctx.dataset.required_columns.items():
        check = tap.check_columns(table, cols)
        ctx.save(f"schema_check_{table.replace('.', '_')}.vot", check.response, "schema_check")


def _single_tap_query(ctx: FetchContext, base_url: str, *, use_async: bool) -> None:
    tap = TapClient(base_url, session=ctx.session)
    _schema_checks(ctx, tap)
    adql = strip_comments(ctx.query_text())
    ctx.save("query.adql", adql.encode(), "request")
    if use_async:
        body = tap.run_async(
            adql,
            on_submit=lambda url: ctx.save("job_url.txt", url.encode(), "request"),
            resume_job_url=ctx.resume_job_url,
        )
    else:
        body = tap.sync(adql)
    ctx.save("result.vot", body)


# Gaia source_ids grow with sky position (HEALPix index in the high bits), and source_id is
# indexed, so contiguous source_id ranges make short, sky-ordered queries. The first chunk has
# no lower bound and the last no upper bound, so the union covers every possible source_id
# whatever the encoding; GAIA_SOURCE_ID_SPAN only sets where the interior cuts fall.
GAIA_CHUNKS = 48
GAIA_SOURCE_ID_SPAN = 12 * 2**59


def source_id_ranges(column: str, chunks: int = GAIA_CHUNKS) -> list[str]:
    """ADQL conditions partitioning all source_ids into `chunks` disjoint, exhaustive ranges."""
    cuts = [k * GAIA_SOURCE_ID_SPAN // chunks for k in range(1, chunks)]
    conds = []
    for k in range(chunks):
        parts = []
        if k > 0:
            parts.append(f"{column} >= {cuts[k - 1]}")
        if k < chunks - 1:
            parts.append(f"{column} < {cuts[k]}")
        conds.append(" AND ".join(parts))
    return conds


def _sync_with_retry(tap: TapClient, adql: str, attempts: int = 3) -> bytes:
    """Read-only sync queries are safe to repeat on transient network or server errors."""
    for attempt in range(1, attempts + 1):
        try:
            return tap.sync(adql)
        except (requests.RequestException, TapError):
            if attempt == attempts:
                raise
            time.sleep(10 * attempt)
    raise AssertionError("unreachable")


def fetch_gaia(ctx: FetchContext) -> None:
    """Run the {source_id_range}-templated query once per source_id chunk (sync, fast)."""
    tap = TapClient(GAIA_TAP, session=ctx.session)
    _schema_checks(ctx, tap)
    template = strip_comments(ctx.query_text())
    if "{source_id_range}" not in template:
        raise ValueError(f"{ctx.dataset.query_file} lacks the {{source_id_range}} placeholder")
    column = "g.source_id" if " AS g" in template else "source_id"
    total = 0
    for n, cond in enumerate(source_id_ranges(column), start=1):
        adql = template.replace("{source_id_range}", cond)
        ctx.save(f"chunk_{n:02d}.adql", adql.encode(), "request")
        ctx.save(f"chunk_{n:02d}.vot", _sync_with_retry(tap, adql))
        total += ctx.files[-1].rows
    ctx.notes.append(f"{GAIA_CHUNKS} disjoint source_id chunks, {total} rows in total")


def fetch_exoplanets(ctx: FetchContext) -> None:
    _single_tap_query(ctx, EXOPLANET_TAP, use_async=False)


def _batches(items: list[str], size: int) -> Iterator[list[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _batched_simbad(ctx: FetchContext, ids: list[str]) -> set[str]:
    """Run the {ids}-templated query in batches; return the query ids SIMBAD matched."""
    from astropy.io.votable import parse_single_table

    tap = TapClient(SIMBAD_TAP, session=ctx.session)
    _schema_checks(ctx, tap)
    template = strip_comments(ctx.query_text())
    matched: set[str] = set()
    for n, batch in enumerate(_batches(ids, ctx.batch_size), start=1):
        adql = template.replace("{ids}", adql_in_list(batch))
        ctx.save(f"batch_{n:04d}.adql", adql.encode(), "request")
        body = tap.sync(adql)
        ctx.save(f"batch_{n:04d}.vot", body)
        table = parse_single_table(io.BytesIO(body)).to_table()
        if "query_id" in table.colnames:
            matched.update(normalize_id(str(v)) for v in table["query_id"])
    return matched


def normalize_id(identifier: str) -> str:
    """SIMBAD returns ids in padded stored form ("M  45"); compare ignoring whitespace."""
    return " ".join(identifier.split())


def column_ci(colnames: list[str], name: str) -> str:
    """Column lookup ignoring case: Gaia returns e.g. SOURCE_ID next to lower-case columns."""
    matches = [c for c in colnames if c.lower() == name.lower()]
    if len(matches) != 1:
        raise KeyError(f"expected exactly one column named {name!r} (any case), got {matches}")
    return matches[0]


def fetch_simbad_ids(ctx: FetchContext) -> None:
    from astropy.io.votable import parse_single_table

    gaia = manifest.latest_complete(manifest.load(ctx.layout), "gaia_dr3_nearby")
    if gaia is None:
        raise RuntimeError("simbad_ids needs a complete gaia_dr3_nearby snapshot first")
    data = [f for f in gaia.files if f.role == "data"]
    source_ids: list[str] = []
    for rec in data:
        table = parse_single_table(str(ctx.layout.root / rec.path)).to_table()
        source_ids.extend(str(int(v)) for v in table[column_ci(table.colnames, "source_id")])
    ctx.notes.append(f"input: {len(source_ids)} source_ids from {', '.join(f.path for f in data)}")
    ids = [f"Gaia DR3 {sid}" for sid in source_ids]
    matched = _batched_simbad(ctx, ids)
    ctx.notes.append(f"SIMBAD matched {len(matched)} of {len(ids)} Gaia DR3 identifiers")


def fetch_landmarks(ctx: FetchContext) -> None:
    spec = yaml.safe_load(ctx.layout.landmarks.read_text(encoding="utf-8"))
    ids = [str(lm["simbad_id"]) for lm in spec["landmarks"]]
    matched = _batched_simbad(ctx, ids)
    missing = [i for i in ids if normalize_id(i) not in matched]
    if missing:
        ctx.partial_reason = f"SIMBAD did not resolve: {missing}"
    ctx.notes.append("coordinates/types only; landmark distances need the §8.3 literature process")


def fetch_horizons(ctx: FetchContext) -> None:
    spec = json.loads(ctx.query_text())
    epoch: dict[str, str] = spec["epoch"]
    urls = []
    versions = set()
    for item in spec["bodies"]:
        body = horizons.Body(item["name"], item["command"])
        content, url = horizons.fetch(body, epoch, session=ctx.session)
        urls.append({"body": body.name, "url": url})
        ctx.save(f"{body.name.lower()}.json", content)
        doc = horizons.parse(content)
        versions.add(str(doc.get("signature", {}).get("version", "unknown")))
        for line in horizons.ephemeris_lines(doc):
            note = f"{body.name}: {line}"
            if note not in ctx.notes:
                ctx.notes.append(note)
    ctx.save("requests.json", json.dumps(urls, indent=2).encode(), "request")
    ctx.release_detail = f"JPL Horizons API signature version(s) {sorted(versions)}"


DATASETS: dict[str, Dataset] = {
    d.id: d
    for d in [
        Dataset(
            id="gaia_dr3_nearby",
            source="ESA Gaia Archive",
            source_dir="gaia",
            service_url=GAIA_TAP,
            release="Gaia DR3",
            query_file="gaia_dr3_nearby.adql",
            fetch=fetch_gaia,
            required_columns={
                "gaiadr3.gaia_source": (
                    "source_id",
                    "designation",
                    "ref_epoch",
                    "ra",
                    "ra_error",
                    "dec",
                    "dec_error",
                    "parallax",
                    "parallax_error",
                    "parallax_over_error",
                    "pmra",
                    "pmra_error",
                    "pmdec",
                    "pmdec_error",
                    "ruwe",
                    "astrometric_params_solved",
                    "phot_g_mean_mag",
                    "phot_bp_mean_mag",
                    "phot_rp_mean_mag",
                    "bp_rp",
                    "radial_velocity",
                    "radial_velocity_error",
                )
            },
        ),
        Dataset(
            id="gaia_dr3_distances",
            source="ESA Gaia Archive (external table, Bailer-Jones et al. 2021)",
            source_dir="gaia",
            service_url=GAIA_TAP,
            release="Bailer-Jones et al. (2021) distances, joined to Gaia DR3 on source_id",
            query_file="gaia_dr3_distances.adql",
            fetch=fetch_gaia,
            required_columns={
                "external.gaiaedr3_distance": (
                    "source_id",
                    "r_med_geo",
                    "r_lo_geo",
                    "r_hi_geo",
                    "r_med_photogeo",
                    "r_lo_photogeo",
                    "r_hi_photogeo",
                    "flag",
                ),
                "gaiadr3.gaia_source": ("source_id", "parallax", "parallax_over_error"),
            },
        ),
        Dataset(
            id="simbad_ids",
            source="SIMBAD (CDS)",
            source_dir="simbad",
            service_url=SIMBAD_TAP,
            release="SIMBAD (live database; retrieval date is the version)",
            query_file="simbad_ids.adql",
            fetch=fetch_simbad_ids,
            required_columns={
                "basic": ("oid", "main_id", "otype", "coo_bibcode"),
                "ident": ("oidref", "id"),
            },
            depends_on=("gaia_dr3_nearby",),
        ),
        Dataset(
            id="horizons_bodies",
            source="JPL Horizons",
            source_dir="horizons",
            service_url=horizons.API_URL,
            release="JPL Horizons",
            query_file="horizons_bodies.json",
            fetch=fetch_horizons,
        ),
        Dataset(
            id="landmarks",
            source="SIMBAD (CDS)",
            source_dir="simbad",
            service_url=SIMBAD_TAP,
            release="SIMBAD (live database; retrieval date is the version)",
            query_file="landmarks.adql",
            fetch=fetch_landmarks,
            required_columns={
                "basic": (
                    "oid",
                    "main_id",
                    "otype",
                    "ra",
                    "dec",
                    "coo_err_maj",
                    "coo_err_min",
                    "coo_bibcode",
                ),
                "ident": ("oidref", "id"),
            },
        ),
        Dataset(
            id="exoplanets_ps",
            source="NASA Exoplanet Archive",
            source_dir="exoplanet_archive",
            service_url=EXOPLANET_TAP,
            release="Planetary Systems (ps) table",
            query_file="exoplanets_ps.adql",
            fetch=fetch_exoplanets,
            required_columns={"ps": ("pl_name", "hostname", "default_flag", "sy_dist")},
        ),
        Dataset(
            id="galaxy_structure",
            source="literature model tables (e.g. VizieR)",
            source_dir="vizier",
            service_url="",
            release="",
            query_file="",
            fetch=None,
            blocked_reason=(
                "needs a human choice of disc/arm model paper (bibcode) before a query exists"
            ),
        ),
    ]
}

__all__ = ["DATASETS", "Dataset", "FetchContext", "TapError", "strip_comments"]
