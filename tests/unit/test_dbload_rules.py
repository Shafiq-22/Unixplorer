"""Loader rules that need no database."""

from __future__ import annotations

import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from ingestion import manifest
from ingestion.dbload import (
    FileRef,
    LoadContext,
    LoadError,
    _check_build_matches_manifest,
    parse_reference,
)
from ingestion.paths import Layout


def _ctx(layout: Layout) -> LoadContext:
    ctx = LoadContext(layout, conn=None, job_id=1, entries={})  # type: ignore[arg-type]
    ctx.files["data/raw/x/ds/2026-01-01/result.vot"] = FileRef(id=7, rows=3, dataset="ds")
    return ctx


def test_manifest_backed_row_resolves(tmp_layout: Layout) -> None:
    assert _ctx(tmp_layout).ref("data/raw/x/ds/2026-01-01/result.vot#row=2", "ds") == (7, 2)


@pytest.mark.parametrize(
    "rid",
    [
        "data/raw/x/ds/2026-01-01/other.vot#row=0",  # file not in manifest
        "data/raw/x/ds/2026-01-01/result.vot#row=3",  # row outside file
        "data/raw/x/ds/2026-01-01/result.vot",  # no row
    ],
)
def test_rows_without_manifest_link_are_rejected(tmp_layout: Layout, rid: str) -> None:
    with pytest.raises(LoadError):
        _ctx(tmp_layout).ref(rid, "ds")


def test_row_from_another_dataset_is_rejected(tmp_layout: Layout) -> None:
    with pytest.raises(LoadError):
        _ctx(tmp_layout).ref("data/raw/x/ds/2026-01-01/result.vot#row=0", "other_ds")


def test_stale_build_is_rejected(tmp_layout: Layout) -> None:
    entry = manifest.Entry(
        dataset="ds",
        source="s",
        service_url="u",
        release="r",
        query_file="q",
        retrieved_at="2026-01-01T00:00:00Z",
        files=[manifest.FileRecord("data/raw/x/a.vot", "a" * 64, 1, 1)],
    )
    table = pa.table({"x": [1]}).replace_schema_metadata(
        {"atlas.inputs": json.dumps([{"path": "data/raw/x/a.vot", "sha256": "b" * 64}])}
    )
    pq.write_table(table, tmp_layout.processed / "ds.parquet")
    with pytest.raises(LoadError, match="rebuild"):
        _check_build_matches_manifest(tmp_layout, {"ds": entry})


def test_reference_parsing_uses_archive_link() -> None:
    html = (
        "<a refstr=BONOMO_ET_AL_2023 href=https://ui.adsabs.harvard.edu/abs/"
        "2023A&A...677A..33B/abstract target=ref>Bonomo et al. 2023</a>"
    )
    assert parse_reference(html) == (
        "BONOMO_ET_AL_2023",
        "2023A&A...677A..33B",
        "Bonomo et al. 2023",
    )
    assert parse_reference(None) == (None, None, None)
