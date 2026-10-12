"""`atlas data fetch`: download one dataset into a new immutable snapshot directory."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import requests

from ingestion import manifest
from ingestion.datasets import DATASETS, FetchContext
from ingestion.paths import Layout


def run_fetch(layout: Layout, dataset_id: str, *, batch_size: int = 1000) -> manifest.Entry:
    ds = DATASETS[dataset_id]
    if ds.fetch is None:
        raise RuntimeError(f"{dataset_id} cannot be fetched yet: {ds.blocked_reason}")
    now = datetime.now(UTC).replace(microsecond=0)
    snapshot = layout.raw / ds.source_dir / ds.id / now.strftime("%Y-%m-%d")
    if snapshot.exists() and any(snapshot.iterdir()):
        raise FileExistsError(
            f"{layout.rel(snapshot)} already holds a snapshot; raw snapshots are never overwritten"
        )
    snapshot.mkdir(parents=True, exist_ok=True)
    ctx = FetchContext(layout, ds, snapshot, requests.Session(), batch_size=batch_size)
    error: BaseException | None = None
    try:
        ds.fetch(ctx)
    except BaseException as exc:  # record what we got, then re-raise
        error = exc
    status = "complete"
    if error is not None:
        status = f"partial: {type(error).__name__}: {str(error)[:500]}"
    elif ctx.partial_reason:
        status = f"partial: {ctx.partial_reason}"
    if not ctx.files:
        _remove_empty_dirs(snapshot, stop=layout.raw)
    entry = manifest.Entry(
        dataset=ds.id,
        source=ds.source,
        service_url=ds.service_url,
        release=ds.release + (f"; {ctx.release_detail}" if ctx.release_detail else ""),
        query_file=layout.rel(layout.queries / ds.query_file),
        retrieved_at=now.isoformat().replace("+00:00", "Z"),
        files=ctx.files,
        license_or_credit="see data/CITATIONS.md",
        status=status,
        notes=ctx.notes,
    )
    manifest.append(layout, entry)
    if error is not None:
        raise error
    return entry


def _remove_empty_dirs(path: Path, *, stop: Path) -> None:
    while path != stop and path.is_dir() and not any(path.iterdir()):
        path.rmdir()
        path = path.parent
