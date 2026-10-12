"""Hit the real archives. Run on demand: `uv run pytest -m live`."""

from __future__ import annotations

import pytest

from ingestion.connectors.tap import TapClient
from ingestion.datasets import DATASETS


@pytest.mark.live
@pytest.mark.parametrize("dataset", [d.id for d in DATASETS.values() if d.required_columns])
def test_schema_has_every_column_we_query(dataset: str) -> None:
    ds = DATASETS[dataset]
    tap = TapClient(ds.service_url, timeout=120)
    for table, cols in ds.required_columns.items():
        assert tap.check_columns(table, cols).missing == []
