from __future__ import annotations

from ingestion import manifest
from ingestion.paths import Layout
from ingestion.verify import verify
from tests.fixtures.synthetic import write_votable


def _entry(layout: Layout) -> manifest.Entry:
    path = write_votable(layout.raw / "test" / "ds" / "2026-01-01" / "result.vot")
    return manifest.Entry(
        dataset="ds",
        source="synthetic",
        service_url="https://example.invalid",
        release="r",
        query_file="data/queries/x.adql",
        retrieved_at="2026-01-01T00:00:00Z",
        files=[manifest.record_file(layout, path)],
    )


def test_roundtrip_and_row_count(tmp_layout: Layout) -> None:
    entry = _entry(tmp_layout)
    assert entry.files[0].rows == 3
    manifest.append(tmp_layout, entry)
    loaded = manifest.load(tmp_layout)
    assert loaded == [entry]
    assert manifest.latest_complete(loaded, "ds") == entry


def test_verify_passes_then_detects_tampering(tmp_layout: Layout) -> None:
    entry = _entry(tmp_layout)
    manifest.append(tmp_layout, entry)
    checks, unlisted = verify(tmp_layout)
    assert [c.ok for c in checks] == [True] and unlisted == []

    path = tmp_layout.root / entry.files[0].path
    path.write_bytes(path.read_bytes() + b" ")
    checks, _ = verify(tmp_layout)
    assert not checks[0].ok and "sha256" in checks[0].detail


def test_verify_flags_missing_and_unlisted(tmp_layout: Layout) -> None:
    entry = _entry(tmp_layout)
    manifest.append(tmp_layout, entry)
    stray = tmp_layout.raw / "test" / "stray.csv"
    stray.write_text("a\n1\n")
    (tmp_layout.root / entry.files[0].path).unlink()
    checks, unlisted = verify(tmp_layout)
    assert checks[0].detail == "missing"
    assert unlisted == ["data/raw/test/stray.csv"]


def test_partial_entries_are_not_latest_complete(tmp_layout: Layout) -> None:
    entry = _entry(tmp_layout)
    entry.status = "partial: test"
    assert manifest.latest_complete([entry], "ds") is None
