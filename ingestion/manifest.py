"""data/manifest.yaml: one entry per fetch, one file record per downloaded file (CLAUDE.md §8.2)."""

from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ingestion.paths import Layout

HEADER = (
    "# Universe Atlas data manifest.\n"
    "# Written by `atlas data fetch`; checked by `atlas data verify`.\n"
    "# One entry per fetch. Never edit by hand; never edit files under data/raw/.\n"
)

# File roles: `data` rows feed the pipeline; the others are provenance evidence.
ROLES = ("data", "schema_check", "request")


@dataclass
class FileRecord:
    path: str
    sha256: str
    bytes: int
    rows: int
    role: str = "data"


@dataclass
class Entry:
    dataset: str
    source: str
    service_url: str
    release: str
    query_file: str
    retrieved_at: str
    files: list[FileRecord] = field(default_factory=list)
    license_or_credit: str = ""
    status: str = "complete"
    notes: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return self.status == "complete"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def count_rows(path: Path) -> int:
    """Row count by file format. A JSON or text document counts as one row."""
    suffix = path.suffix.lower()
    if suffix in (".vot", ".xml"):
        from astropy.io.votable import parse_single_table

        return len(parse_single_table(str(path)).array)
    if suffix == ".csv":
        with path.open(newline="", encoding="utf-8") as fh:
            return max(sum(1 for _ in csv.reader(fh)) - 1, 0)
    return 1


def record_file(layout: Layout, path: Path, role: str = "data") -> FileRecord:
    if role not in ROLES:
        raise ValueError(f"unknown file role {role!r}")
    return FileRecord(
        path=layout.rel(path),
        sha256=sha256_file(path),
        bytes=path.stat().st_size,
        rows=count_rows(path),
        role=role,
    )


def load(layout: Layout) -> list[Entry]:
    if not layout.manifest.exists():
        return []
    raw = yaml.safe_load(layout.manifest.read_text(encoding="utf-8")) or []
    if not isinstance(raw, list):
        raise ValueError("data/manifest.yaml must be a YAML list of entries")
    entries = []
    for item in raw:
        files = [FileRecord(**f) for f in item.pop("files", [])]
        entries.append(Entry(files=files, **item))
    return entries


def save(layout: Layout, entries: list[Entry]) -> None:
    body = yaml.safe_dump(
        [_entry_dict(e) for e in entries], sort_keys=False, allow_unicode=True, width=100
    )
    tmp = layout.manifest.with_suffix(".yaml.tmp")
    tmp.write_text(HEADER + ("[]\n" if not entries else body), encoding="utf-8")
    tmp.replace(layout.manifest)


def append(layout: Layout, entry: Entry) -> None:
    entries = load(layout)
    entries.append(entry)
    save(layout, entries)


def latest_complete(entries: list[Entry], dataset: str) -> Entry | None:
    matches = [e for e in entries if e.dataset == dataset and e.complete]
    return max(matches, key=lambda e: e.retrieved_at) if matches else None


def _entry_dict(entry: Entry) -> dict[str, Any]:
    d = asdict(entry)
    if not d["notes"]:
        d.pop("notes")
    return d


def dump_entry(entry: Entry) -> str:
    buf = io.StringIO()
    yaml.safe_dump([_entry_dict(entry)], buf, sort_keys=False)
    return buf.getvalue()
