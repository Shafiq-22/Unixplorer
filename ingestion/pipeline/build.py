"""`atlas data build`: data/raw -> data/processed/<dataset>.parquet, deterministically.

The same raw files always produce byte-identical Parquet: no timestamps, fixed row order
(manifest file order, then raw row order), fixed compression. Original values and units are
kept; numeric columns with a convertible physical unit gain a `<name>__si` companion.
Every row carries `source_record_id` = "<raw file path>#row=<0-based row>".
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from ingestion import manifest
from ingestion.connectors import horizons
from ingestion.paths import Layout

BUILD_VERSION = "1"
_NO_SI = {"mag", "dex", ""}


@dataclass(frozen=True)
class BuildResult:
    dataset: str
    path: str
    rows: int
    inputs: int


def build_all(layout: Layout) -> list[BuildResult]:
    entries = manifest.load(layout)
    results = []
    for dataset in sorted({e.dataset for e in entries}):
        entry = manifest.latest_complete(entries, dataset)
        if entry is not None:
            results.append(build_dataset(layout, entry))
    return results


def build_dataset(layout: Layout, entry: manifest.Entry) -> BuildResult:
    data_files = [f for f in entry.files if f.role == "data"]
    tables = [_load(layout, rec) for rec in data_files]
    table = pa.concat_tables(tables, promote_options="permissive") if tables else pa.table({})
    meta = {
        "atlas.dataset": entry.dataset,
        "atlas.build_version": BUILD_VERSION,
        "atlas.retrieved_at": entry.retrieved_at,
        "atlas.release": entry.release,
        "atlas.inputs": json.dumps([{"path": f.path, "sha256": f.sha256} for f in data_files]),
    }
    table = table.replace_schema_metadata(meta)
    layout.processed.mkdir(parents=True, exist_ok=True)
    out = layout.processed / f"{entry.dataset}.parquet"
    pq.write_table(
        table,
        out,
        compression="zstd",
        compression_level=9,
        row_group_size=100_000,
        write_statistics=True,
        use_dictionary=True,
    )
    return BuildResult(entry.dataset, layout.rel(out), table.num_rows, len(data_files))


def _load(layout: Layout, rec: manifest.FileRecord) -> pa.Table:
    path = layout.root / rec.path
    suffix = path.suffix.lower()
    if suffix in (".vot", ".xml"):
        table = votable_to_arrow(path)
    elif suffix == ".json":
        table = horizons_to_arrow(path)
    else:
        raise ValueError(f"no builder for {rec.path}")
    ids = pa.array([f"{rec.path}#row={i}" for i in range(table.num_rows)], pa.string())
    return table.append_column(pa.field("source_record_id", pa.string()), ids)


def votable_to_arrow(path: Path) -> pa.Table:
    from astropy.io.votable import parse_single_table

    vt = parse_single_table(str(path))
    t = vt.to_table()
    ucds = {f.name: (f.ucd or "") for f in vt.fields}
    fields: list[pa.Field] = []
    arrays: list[pa.Array] = []
    for name in t.colnames:
        col = t[name]
        unit = col.unit.to_string() if col.unit is not None else ""
        arr = _to_arrow(np.ma.asarray(col))
        md = {"unit": unit, "ucd": ucds.get(name, "")}
        fields.append(pa.field(name, arr.type, metadata=md))
        arrays.append(arr)
        si = _si_companion(name, arr, unit, ucds.get(name, ""))
        if si is not None:
            fields.append(si[0])
            arrays.append(si[1])
    return pa.Table.from_arrays(arrays, schema=pa.schema(fields))


def _to_arrow(values: np.ma.MaskedArray) -> pa.Array:
    mask = np.ma.getmaskarray(values)
    data = np.ma.getdata(values)
    if data.dtype.kind == "f":
        mask = mask | np.isnan(data)  # NaN is never data: missing means null
        return pa.array(data, mask=mask)
    if data.dtype.kind in "iub":
        return pa.array(data, mask=mask)
    out: list[Any] = []
    for v, m in zip(data.tolist(), mask.tolist(), strict=True):
        if m or v is None:
            out.append(None)
        else:
            out.append(v.decode() if isinstance(v, bytes) else str(v))
    return pa.array(out, pa.string())


def _si_companion(
    name: str, arr: pa.Array, unit: str, ucd: str
) -> tuple[pa.Field, pa.Array] | None:
    import astropy.units as u

    if not pa.types.is_floating(arr.type) and not pa.types.is_integer(arr.type):
        return None
    if unit in _NO_SI or "epoch" in ucd or "epoch" in name.lower():
        return None
    try:
        q = (1.0 * u.Unit(unit)).si
    except (ValueError, TypeError, u.UnitsError):
        return None
    if q.unit == u.Unit(unit) and q.value == 1.0:
        return None
    values = np.asarray(arr.to_numpy(zero_copy_only=False), dtype=np.float64) * q.value
    si = pa.array(values, mask=np.asarray(arr.is_null()), type=pa.float64())
    md = {"unit": q.unit.to_string(), "derived_from": name, "conversion": "astropy.units .si"}
    return pa.field(f"{name}__si", pa.float64(), metadata=md), si


_HORIZONS_UNITS = {"KM-S": ("km", "km / s"), "AU-D": ("AU", "AU / d"), "KM-D": ("km", "km / d")}


def horizons_to_arrow(path: Path) -> pa.Table:
    doc = horizons.parse(path.read_bytes())
    header, rows = horizons.vector_rows(doc)
    out_units = _requested_out_units(path)
    pos_unit, vel_unit = _HORIZONS_UNITS.get(out_units, ("", ""))
    target = horizons.resolved_target(doc)
    fields = [pa.field("target", pa.string())]
    arrays: list[pa.Array] = [pa.array([target] * len(rows), pa.string())]
    for i, name in enumerate(header):
        cells = [r[i] if i < len(r) else None for r in rows]
        unit = (
            pos_unit if name in ("X", "Y", "Z") else vel_unit if name in ("VX", "VY", "VZ") else ""
        )
        if name.startswith("JD") or name in ("X", "Y", "Z", "VX", "VY", "VZ"):
            arr = pa.array([float(c) if c else None for c in cells], pa.float64())
        else:
            arr = pa.array(cells, pa.string())
        if name.startswith("JD"):
            unit = "d"
        fields.append(pa.field(name, arr.type, metadata={"unit": unit, "ucd": ""}))
        arrays.append(arr)
        si = _si_companion(name, arr, unit, "time.epoch" if name.startswith("JD") else "")
        if si is not None:
            fields.append(si[0])
            arrays.append(si[1])
    return pa.Table.from_arrays(arrays, schema=pa.schema(fields))


def _requested_out_units(path: Path) -> str:
    """OUT_UNITS as actually sent, read from the snapshot's own requests.json ("" if unknown)."""
    from urllib.parse import parse_qs, urlsplit

    req = path.parent / "requests.json"
    if not req.is_file():
        return ""
    for item in json.loads(req.read_text(encoding="utf-8")):
        values = parse_qs(urlsplit(item["url"]).query).get("OUT_UNITS")
        if values:
            return str(values[0]).strip("'")
    return ""
