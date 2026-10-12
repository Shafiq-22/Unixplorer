from __future__ import annotations

import json

import pytest

from ingestion.connectors import horizons
from ingestion.connectors.tap import TapError, _checked_votable, adql_in_list
from ingestion.datasets import normalize_id, strip_comments
from tests.fixtures.synthetic import HORIZONS_RESULT

ERROR_VOTABLE = b"""<?xml version="1.0"?>
<VOTABLE version="1.4" xmlns="http://www.ivoa.net/xml/VOTable/v1.3">
 <RESOURCE type="results"><INFO name="QUERY_STATUS" value="ERROR">bad column</INFO></RESOURCE>
</VOTABLE>"""


def test_tap_error_document_is_rejected() -> None:
    with pytest.raises(TapError, match="QUERY_STATUS=ERROR"):
        _checked_votable(ERROR_VOTABLE)


def test_non_votable_is_rejected() -> None:
    with pytest.raises(TapError):
        _checked_votable(b"<html>proxy error</html>")


def test_adql_quoting() -> None:
    assert adql_in_list(["M 45", "* eta Car", "O'Brien"]) == "'M 45', '* eta Car', 'O''Brien'"


def test_strip_comments_keeps_query() -> None:
    assert strip_comments("-- note\nSELECT a\n  -- x\nFROM t") == "SELECT a\nFROM t"


def test_horizons_target_check() -> None:
    doc = horizons.parse(json.dumps({"result": HORIZONS_RESULT}).encode())
    horizons.check_target(doc, horizons.Body("Testbody", "9999"))
    with pytest.raises(horizons.HorizonsError, match="resolved"):
        horizons.check_target(doc, horizons.Body("Mars", "499"))


def test_horizons_error_field() -> None:
    with pytest.raises(horizons.HorizonsError):
        horizons.parse(b'{"error": "no such object"}')


def test_simbad_padded_ids_match_unpadded() -> None:
    assert normalize_id("M  45") == normalize_id("M 45") == "M 45"
    assert normalize_id("Cl Melotte   25") == "Cl Melotte 25"


OVERFLOW_VOTABLE = b"""<?xml version="1.0"?>
<VOTABLE version="1.4" xmlns="http://www.ivoa.net/xml/VOTable/v1.3">
 <RESOURCE type="results"><INFO name="QUERY_STATUS" value="OVERFLOW"/></RESOURCE>
</VOTABLE>"""


def test_truncated_result_is_rejected() -> None:
    with pytest.raises(TapError, match="OVERFLOW"):
        _checked_votable(OVERFLOW_VOTABLE)
