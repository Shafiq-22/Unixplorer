"""`atlas` command-line interface (CLAUDE.md §3)."""

from __future__ import annotations

import argparse
import sys

from ingestion import manifest
from ingestion.datasets import DATASETS
from ingestion.paths import Layout, find_repo_root


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="atlas")
    parser.add_argument("--root", help="repo root (default: auto-detect or $ATLAS_ROOT)")
    top = parser.add_subparsers(dest="group", required=True)
    data = top.add_parser("data", help="data snapshot commands").add_subparsers(
        dest="cmd", required=True
    )
    fetch = data.add_parser("fetch", help="download a dataset into data/raw and the manifest")
    fetch.add_argument("dataset", choices=sorted(DATASETS))
    fetch.add_argument("--batch-size", type=int, default=1000, help="ids per SIMBAD query")
    fetch.add_argument(
        "--resume-job", metavar="URL", help="wait on an existing TAP async job (see job_url.txt)"
    )
    data.add_parser("verify", help="check manifest hashes, sizes and row counts")
    data.add_parser("build", help="build data/processed/*.parquet from data/raw")
    data.add_parser("status", help="what is downloaded, when, from which release")
    args = parser.parse_args(argv)

    from pathlib import Path

    layout = Layout(Path(args.root).resolve() if args.root else find_repo_root())
    if args.cmd == "fetch":
        return _fetch(layout, args.dataset, args.batch_size, args.resume_job)
    if args.cmd == "verify":
        return _verify(layout)
    if args.cmd == "build":
        return _build(layout)
    return _status(layout)


def _fetch(layout: Layout, dataset: str, batch_size: int, resume_job: str | None) -> int:
    from ingestion.fetch import run_fetch

    try:
        entry = run_fetch(layout, dataset, batch_size=batch_size, resume_job_url=resume_job)
    except Exception as exc:  # noqa: BLE001 - report and exit non-zero; manifest already updated
        print(f"fetch {dataset} FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(manifest.dump_entry(entry))
    return 0 if entry.complete else 1


def _verify(layout: Layout) -> int:
    from ingestion.verify import verify

    checks, unlisted = verify(layout)
    for c in checks:
        print(f"{'OK  ' if c.ok else 'FAIL'} {c.dataset:20s} {c.path}  {c.detail}")
    for path in unlisted:
        print(f"FAIL {'(no manifest entry)':20s} {path}")
    bad = sum(not c.ok for c in checks) + len(unlisted)
    print(f"{len(checks)} manifest file(s) checked, {bad} problem(s)")
    return 1 if bad else 0


def _build(layout: Layout) -> int:
    from ingestion.pipeline.build import build_all

    results = build_all(layout)
    for r in results:
        print(f"{r.dataset:20s} {r.rows:>9d} rows from {r.inputs} file(s) -> {r.path}")
    if not results:
        print("nothing to build: no complete snapshot in data/manifest.yaml")
    return 0


def _status(layout: Layout) -> int:
    entries = manifest.load(layout)
    for ds in DATASETS.values():
        latest = max(
            (e for e in entries if e.dataset == ds.id), key=lambda e: e.retrieved_at, default=None
        )
        if latest is None:
            state = f"blocked: {ds.blocked_reason}" if ds.blocked_reason else "not downloaded"
            print(f"{ds.id:20s} {state}")
            continue
        size = sum(f.bytes for f in latest.files)
        rows = sum(f.rows for f in latest.files if f.role == "data")
        print(
            f"{ds.id:20s} {latest.status[:60]:60s} {latest.retrieved_at}  "
            f"{rows} rows  {size} bytes  [{latest.release}]"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
