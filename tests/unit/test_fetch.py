from __future__ import annotations

import dataclasses

import pytest

from ingestion import datasets, manifest
from ingestion.datasets import DATASETS, FetchContext
from ingestion.fetch import run_fetch
from ingestion.paths import Layout


def _patch(monkeypatch: pytest.MonkeyPatch, fn: datasets.Fetcher) -> None:
    ds = dataclasses.replace(DATASETS["exoplanets_ps"], fetch=fn)
    monkeypatch.setitem(DATASETS, "exoplanets_ps", ds)


def test_failed_fetch_is_recorded_partial_without_files(
    tmp_layout: Layout, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(ctx: FetchContext) -> None:
        raise ConnectionError("403 Forbidden")

    _patch(monkeypatch, boom)
    with pytest.raises(ConnectionError):
        run_fetch(tmp_layout, "exoplanets_ps")
    [entry] = manifest.load(tmp_layout)
    assert entry.status.startswith("partial: ConnectionError: 403")
    assert entry.files == []
    assert not any(tmp_layout.raw.rglob("*"))


def test_partial_download_keeps_what_arrived(
    tmp_layout: Layout, monkeypatch: pytest.MonkeyPatch
) -> None:
    def half(ctx: FetchContext) -> None:
        ctx.save("batch_0001.csv", b"a\n1\n2\n")
        raise TimeoutError("batch 2")

    _patch(monkeypatch, half)
    with pytest.raises(TimeoutError):
        run_fetch(tmp_layout, "exoplanets_ps")
    [entry] = manifest.load(tmp_layout)
    assert entry.status.startswith("partial") and entry.files[0].rows == 2


def test_raw_snapshot_is_never_overwritten(
    tmp_layout: Layout, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch(monkeypatch, lambda ctx: ctx.save("result.csv", b"a\n1\n") and None)
    first = run_fetch(tmp_layout, "exoplanets_ps")
    second = run_fetch(tmp_layout, "exoplanets_ps")
    first_path = tmp_layout.root / first.files[0].path
    second_path = tmp_layout.root / second.files[0].path
    assert first_path != second_path
    assert first_path.parent.name + ".2" == second_path.parent.name
    assert first_path.read_bytes() == b"a\n1\n"


def test_unfetchable_dataset_refuses(tmp_layout: Layout) -> None:
    with pytest.raises(RuntimeError, match="human choice"):
        run_fetch(tmp_layout, "galaxy_structure")
