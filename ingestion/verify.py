"""`atlas data verify`: every manifest file exists and matches its sha256, size and row count."""

from __future__ import annotations

from dataclasses import dataclass

from ingestion import manifest
from ingestion.paths import Layout

IGNORED = {".gitkeep", ".DS_Store"}


@dataclass(frozen=True)
class FileCheck:
    dataset: str
    path: str
    ok: bool
    detail: str


def verify(layout: Layout) -> tuple[list[FileCheck], list[str]]:
    """Return (per-file checks, raw files that no manifest entry accounts for)."""
    checks: list[FileCheck] = []
    listed: set[str] = set()
    for entry in manifest.load(layout):
        for rec in entry.files:
            listed.add(rec.path)
            checks.append(_check(layout, entry.dataset, rec))
    unlisted = (
        sorted(
            layout.rel(p)
            for p in layout.raw.rglob("*")
            if p.is_file() and p.name not in IGNORED and layout.rel(p) not in listed
        )
        if layout.raw.exists()
        else []
    )
    return checks, unlisted


def _check(layout: Layout, dataset: str, rec: manifest.FileRecord) -> FileCheck:
    path = layout.root / rec.path
    if not path.is_file():
        return FileCheck(dataset, rec.path, False, "missing")
    problems = []
    size = path.stat().st_size
    if size != rec.bytes:
        problems.append(f"bytes {size} != {rec.bytes}")
    digest = manifest.sha256_file(path)
    if digest != rec.sha256:
        problems.append(f"sha256 {digest[:12]}… != {rec.sha256[:12]}…")
    rows = manifest.count_rows(path)
    if rows != rec.rows:
        problems.append(f"rows {rows} != {rec.rows}")
    if problems:
        return FileCheck(dataset, rec.path, False, "; ".join(problems))
    return FileCheck(dataset, rec.path, True, f"sha256 {digest} rows {rows} bytes {size}")
