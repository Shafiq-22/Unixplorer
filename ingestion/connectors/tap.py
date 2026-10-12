"""Minimal IVOA TAP client that returns response bytes exactly as the service sent them.

Used for the Gaia Archive, SIMBAD and the NASA Exoplanet Archive. Before any data query,
`check_columns` asks the service's own TAP_SCHEMA whether the tables and columns we name
exist, so a remembered-but-wrong column name fails loudly instead of being trusted.
"""

from __future__ import annotations

import io
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENT = "universe-atlas-ingestion/0.0.1 (+https://github.com/Shafiq-22/Unixplorer)"


class TapError(RuntimeError):
    pass


@dataclass(frozen=True)
class SchemaCheck:
    table: str
    required: frozenset[str]
    found: frozenset[str]
    response: bytes

    @property
    def missing(self) -> list[str]:
        found = {c.lower() for c in self.found}
        return sorted(c for c in self.required if c.lower() not in found)


class TapClient:
    def __init__(
        self,
        base_url: str,
        *,
        session: requests.Session | None = None,
        timeout: float = 600.0,
        result_format: str = "votable",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        _mount_get_retries(self.session)
        self.session.headers.setdefault("User-Agent", USER_AGENT)
        self.timeout = timeout
        self.result_format = result_format

    def _params(self, adql: str) -> dict[str, str]:
        return {
            "REQUEST": "doQuery",
            "LANG": "ADQL",
            "FORMAT": self.result_format,
            "QUERY": adql,
        }

    def sync(self, adql: str) -> bytes:
        resp = self.session.post(
            f"{self.base_url}/sync", data=self._params(adql), timeout=self.timeout
        )
        _raise_for_status(resp)
        return _checked_votable(resp.content)

    def run_async(
        self,
        adql: str,
        *,
        poll_s: float = 5.0,
        max_wait_s: float = 7200.0,
        on_submit: Callable[[str], object] | None = None,
        resume_job_url: str | None = None,
    ) -> bytes:
        """Submit a UWS job (or resume an existing one), wait for it, return the result document.

        `on_submit` receives the job URL as soon as it exists, so an interrupted fetch can be
        resumed with `resume_job_url` instead of re-running a long query.
        """
        if resume_job_url:
            job_url = resume_job_url.rstrip("/")
        else:
            params = self._params(adql) | {"PHASE": "RUN"}
            resp = self.session.post(
                f"{self.base_url}/async", data=params, timeout=self.timeout, allow_redirects=False
            )
            if resp.status_code not in (200, 201, 303):
                _raise_for_status(resp)
            job_url = resp.headers.get("Location") or resp.url
            if not job_url or job_url.rstrip("/").endswith("/async"):
                raise TapError("TAP async submission did not return a job URL")
        if on_submit is not None:
            on_submit(job_url)
        deadline = time.monotonic() + max_wait_s
        while True:
            phase_resp = self.session.get(f"{job_url}/phase", timeout=self.timeout)
            _raise_for_status(phase_resp)
            phase = phase_resp.text.strip().upper()
            if phase == "COMPLETED":
                break
            if phase in ("ERROR", "ABORTED"):
                err = self.session.get(f"{job_url}/error", timeout=self.timeout)
                raise TapError(f"TAP job {phase}: {err.text[:2000]}")
            if time.monotonic() > deadline:
                raise TapError(f"TAP job still {phase} after {max_wait_s:.0f}s: {job_url}")
            time.sleep(poll_s)
        result = self.session.get(f"{job_url}/results/result", timeout=self.timeout)
        _raise_for_status(result)
        return _checked_votable(result.content)

    def check_columns(self, table: str, required: Iterable[str]) -> SchemaCheck:
        names = {table}
        if "." in table:
            names.add(table.split(".", 1)[1])
        in_list = ", ".join(_adql_str(n) for n in sorted(names))
        adql = (
            "SELECT table_name, column_name, unit FROM TAP_SCHEMA.columns "
            f"WHERE table_name IN ({in_list})"
        )
        body = self.sync(adql)
        found = frozenset(
            str(v).strip() for v in _votable_column(body, "column_name") if v is not None
        )
        check = SchemaCheck(table, frozenset(required), found, body)
        if not found:
            raise TapError(f"TAP_SCHEMA lists no columns for table {table!r}; check the name")
        if check.missing:
            raise TapError(f"table {table!r} lacks columns {check.missing}")
        return check


def adql_in_list(values: Iterable[str]) -> str:
    return ", ".join(_adql_str(v) for v in values)


def _adql_str(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _raise_for_status(resp: requests.Response) -> None:
    if resp.status_code >= 400:
        raise TapError(f"HTTP {resp.status_code} from {resp.url}: {resp.text[:2000]}")


def _checked_votable(body: bytes) -> bytes:
    """Reject error documents; return the body unchanged otherwise."""
    from astropy.io.votable import parse

    try:
        vot = parse(io.BytesIO(body))
    except Exception as exc:  # noqa: BLE001 - surface any parse failure with context
        raise TapError(f"response is not a parseable VOTable: {body[:500]!r}") from exc
    for info in [*vot.infos, *(i for r in vot.resources for i in r.infos)]:
        if info.name == "QUERY_STATUS" and str(info.value).upper() == "ERROR":
            raise TapError(f"TAP QUERY_STATUS=ERROR: {info.content or ''}")
    return body


def _votable_column(body: bytes, name: str) -> list[object]:
    from astropy.io.votable import parse_single_table

    table = parse_single_table(io.BytesIO(body)).to_table()
    if name not in table.colnames:
        return []
    return [None if v is None else (v.decode() if isinstance(v, bytes) else v) for v in table[name]]


def _mount_get_retries(session: requests.Session) -> None:
    """Retry idempotent GETs (job phase polls, result downloads) on transient network errors.

    POSTs (query submission) are never retried: resubmitting would start a duplicate job.
    """
    retry = Retry(
        total=6,
        connect=6,
        read=6,
        status=6,
        backoff_factor=2.0,
        status_forcelist=(502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
