"""JPL Horizons API connector: barycentric ICRF state vectors at one fixed epoch.

The response JSON is saved byte-for-byte. Horizons echoes the resolved target in the
result text ("Target body name: ..."); `check_target` refuses a response whose target
is not the body we asked for, so a wrong ID cannot silently become a wrong planet.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import requests

from ingestion.connectors.tap import USER_AGENT

API_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"

_TARGET_RE = re.compile(r"Target body name:\s*(?P<name>.+?)\s*(?:\(|\{|$)", re.MULTILINE)


class HorizonsError(RuntimeError):
    pass


@dataclass(frozen=True)
class Body:
    name: str
    command: str


def request_params(body: Body, epoch: dict[str, str]) -> dict[str, str]:
    """Parameters for one VECTORS request. `epoch` comes from data/queries/horizons_bodies.json."""
    params = {
        "format": "json",
        "COMMAND": f"'{body.command}'",
        "OBJ_DATA": "'YES'",
        "MAKE_EPHEM": "'YES'",
        "EPHEM_TYPE": "'VECTORS'",
    }
    params.update({k: f"'{v}'" for k, v in epoch.items()})
    return params


def fetch(
    body: Body, epoch: dict[str, str], *, session: requests.Session | None = None
) -> tuple[bytes, str]:
    """Return (response bytes as sent, final request URL)."""
    s = session or requests.Session()
    s.headers.setdefault("User-Agent", USER_AGENT)
    resp = s.get(API_URL, params=request_params(body, epoch), timeout=120)
    if resp.status_code >= 400:
        raise HorizonsError(f"HTTP {resp.status_code} from Horizons: {resp.text[:1000]}")
    doc = parse(resp.content)
    check_target(doc, body)
    return resp.content, resp.url


def parse(content: bytes) -> dict[str, Any]:
    doc: dict[str, Any] = json.loads(content)
    if "error" in doc:
        raise HorizonsError(f"Horizons error: {doc['error']}")
    if "result" not in doc:
        raise HorizonsError("Horizons response has no 'result' field")
    return doc


def resolved_target(doc: dict[str, Any]) -> str | None:
    m = _TARGET_RE.search(str(doc["result"]))
    return m.group("name").strip() if m else None


def check_target(doc: dict[str, Any], body: Body) -> None:
    target = resolved_target(doc)
    if target is None or not target.lower().startswith(body.name.lower()):
        raise HorizonsError(
            f"asked for {body.name!r} ({body.command}); Horizons resolved {target!r}"
        )


def ephemeris_lines(doc: dict[str, Any]) -> list[str]:
    """Header lines naming the ephemeris source/version, quoted verbatim for the manifest."""
    lines = str(doc["result"]).splitlines()
    head = lines[: next((i for i, ln in enumerate(lines) if "$$SOE" in ln), len(lines))]
    return [ln.strip() for ln in head if re.search(r"ephem|DE\d{3}", ln, re.IGNORECASE)][:5]


def vector_rows(doc: dict[str, Any]) -> tuple[list[str], list[list[str]]]:
    """Split a CSV_FORMAT=YES vector table into (header, rows) using $$SOE/$$EOE markers."""
    lines = str(doc["result"]).splitlines()
    try:
        soe = next(i for i, ln in enumerate(lines) if ln.strip() == "$$SOE")
        eoe = next(i for i, ln in enumerate(lines) if ln.strip() == "$$EOE")
    except StopIteration as exc:
        raise HorizonsError("no $$SOE/$$EOE block in Horizons result") from exc
    header_line = next(
        ln for ln in reversed(lines[:soe]) if ln.strip() and not ln.strip().startswith("*")
    )
    header = [h.strip() for h in header_line.split(",") if h.strip()]
    rows = []
    for ln in lines[soe + 1 : eoe]:
        cells = [c.strip() for c in ln.split(",")]
        rows.append(cells[: len(header)])
    return header, rows


_SOURCE_RE = re.compile(r"\{source:\s*(?P<src>[^}]+?)\s*\}")
_HEADER_FIELDS = {
    "reference_frame": re.compile(r"^Reference frame\s*:\s*(?P<v>.+?)\s*$", re.MULTILINE),
    "start_time": re.compile(r"^Start time\s*:\s*(?P<v>.+?)\s*$", re.MULTILINE),
    "output_units": re.compile(r"^Output units\s*:\s*(?P<v>.+?)\s*$", re.MULTILINE),
}


def header_fields(doc: dict[str, Any]) -> dict[str, str | None]:
    """Provenance stated by Horizons itself in the result header (verbatim text)."""
    result = str(doc["result"])
    out: dict[str, str | None] = {}
    for key, rx in _HEADER_FIELDS.items():
        m = rx.search(result)
        out[key] = m.group("v") if m else None
    for key, label in (
        ("target_ephemeris", "Target body name"),
        ("center_ephemeris", "Center body name"),
    ):
        line = next((ln for ln in result.splitlines() if ln.strip().startswith(label)), "")
        m = _SOURCE_RE.search(line)
        out[key] = m.group("src") if m else None
    return out
