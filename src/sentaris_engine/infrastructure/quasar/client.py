"""Reading one page, and windows of pages, of `GET /v1/candles` from the Quasar Market Data REST API over HTTP (DR-18).

`fetch_page` is one request, one page; `read_candles` reads a window as a series of such pages. No retry. A failure is
an exception deriving from `QuasarError` (see `errors`), never empty data. Proxies are not touched: urllib's default
handlers apply the environment's settings, and no redirect is followed (contract section 1: the API never redirects).
The only clock read is `time.monotonic()`, which decides whether a request has outlived its deadline and never reaches
a result.

Time bounds: `timeout_s` limits each blocking socket operation; `deadline_s` is checked after `urlopen` returns and
around every body read, so it bounds a body that drips slowly. The response head (status line and headers) is read
inside `urlopen` and is bounded only per socket operation by `timeout_s`, and name resolution is not bounded at all.
"""

from __future__ import annotations

import http.client
import math
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from email.message import Message
from types import MappingProxyType
from typing import Protocol
from urllib.parse import quote, urlencode, urlsplit

from sentaris_engine.domain.timing import require_instant
from sentaris_engine.infrastructure.quasar.decoding import decode_candle_page, decode_error
from sentaris_engine.infrastructure.quasar.errors import QuasarUnavailableError
from sentaris_engine.infrastructure.quasar.pages import CandlePage, CandleRead, PageRequest

MAX_PAGE_LIMIT = 1000
MAX_WINDOW_SLOTS = 10_000
TIMEFRAME_MS: Mapping[str, int] = MappingProxyType({"5m": 300_000})

# Contract section 1 "Time" and section 5.1: the instants Quasar accepts.
_MIN_START_MS = 946_684_800_000
_MAX_START_MS = 4_102_444_800_000
_CHUNK_BYTES = 64 * 1024
_OK = 200


class _Response(Protocol):
    """What the client uses of a response: a `urlopen` result or an `HTTPError`, which is one."""

    @property
    def status(self) -> int | None: ...

    @property
    def headers(self) -> Message: ...

    def read1(self, size: int = ..., /) -> bytes: ...

    def close(self) -> None: ...


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never follows a redirect: `None` makes the `3xx` surface as an `HTTPError`."""

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: object,
        code: int,
        msg: str,
        headers: Message,
        newurl: str,
    ) -> None:
        return None


def _seconds(value: object, name: str) -> float:
    if type(value) is not int and type(value) is not float:
        raise ValueError(f"{name} must be an int or float of seconds, got {type(value).__name__}")
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and greater than zero, got {value}")
    return float(value)


def _base_url(value: object) -> str:
    if type(value) is not str:
        raise ValueError(f"base_url must be a str, got {type(value).__name__}")
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError(f"base_url must be an http or https URL with a host, got {value!r}")
    if parts.path not in ("", "/") or parts.query or parts.fragment:
        raise ValueError(f"base_url must have no path, query or fragment, got {value!r}")
    if parts.username is not None or parts.password is not None:
        raise ValueError(f"base_url must have no user information, got {value!r}")
    if any(char.isspace() or not char.isprintable() for char in parts.hostname):
        raise ValueError(f"base_url host must have no whitespace or control characters, got {value!r}")
    try:
        parts.hostname.encode("idna")
    except UnicodeError as error:
        raise ValueError(f"base_url host is not a valid host name, got {value!r}") from error
    parts.port  # noqa: B018 - raises ValueError for a port that is not a number in range
    return f"{parts.scheme}://{parts.netloc}"


def _text(value: object, name: str) -> str:
    if type(value) is not str or value == "":
        raise ValueError(f"{name} must be a non-empty str, got {value!r}")
    return value


class QuasarClient:
    """Reads stored candles page by page. It claims nothing about a snapshot, consistency or availability."""

    def __init__(self, base_url: str, *, timeout_s: float = 10.0, deadline_s: float = 30.0) -> None:
        self._base_url = _base_url(base_url)
        self._timeout_s = _seconds(timeout_s, "timeout_s")
        self._deadline_s = _seconds(deadline_s, "deadline_s")
        if self._timeout_s > self._deadline_s:
            raise ValueError(f"timeout_s {timeout_s} must not exceed deadline_s {deadline_s}")
        self._opener = urllib.request.build_opener(_NoRedirect())

    def fetch_page(
        self,
        venue: str,
        symbol: str,
        timeframe: str,
        start: int,
        end: int,
        limit: int = MAX_PAGE_LIMIT,
    ) -> CandlePage:
        """One `GET /v1/candles` request, decoded and checked against what was asked.

        Every precondition is a `ValueError` and nothing is sent. The window is not capped here: one over
        `MAX_WINDOW_SLOTS` is sent and Quasar answers `400`. A failure is a `QuasarError`; see `errors`.
        """
        request = self._validated(venue, symbol, timeframe, start, end, limit)
        query = urlencode(
            [
                ("venue", venue),
                ("symbol", symbol),
                ("timeframe", timeframe),
                ("start", str(start)),
                ("end", str(end)),
                ("limit", str(limit)),
            ],
            quote_via=quote,
            safe="",
        )
        status, body, retry_after = self._get(f"{self._base_url}/v1/candles?{query}")
        if status == _OK:
            return decode_candle_page(body, request)
        raise decode_error(status, body, retry_after)

    def read_candles(self, venue: str, symbol: str, timeframe: str, start: int, end: int) -> CandleRead:
        """The pages of `[start, end)`, read in order; any failure propagates and nothing partial is returned.

        The window is split into chunks of at most `MAX_WINDOW_SLOTS` slots; inside a chunk pages of `MAX_PAGE_LIMIT`
        are requested from the chunk start, then from each page's `next_start`, with the chunk end always as `end`.
        The preconditions are those of `fetch_page` and are checked for the whole window before anything is sent.

        The result is the pages as read. The pages are separate reads at separate moments (contract section 3), so it
        is NOT a snapshot and says nothing about consistency, availability or completeness (OD-24, DR-21).
        """
        timeframe_ms = self._validated(venue, symbol, timeframe, start, end, MAX_PAGE_LIMIT).timeframe_ms
        chunk_ms = MAX_WINDOW_SLOTS * timeframe_ms
        pages: list[CandlePage] = []
        chunk_start = start
        while chunk_start < end:
            chunk_end = min(chunk_start + chunk_ms, end)
            page_start: int | None = chunk_start
            while page_start is not None:
                page = self.fetch_page(venue, symbol, timeframe, page_start, chunk_end, MAX_PAGE_LIMIT)
                pages.append(page)
                page_start = page.next_start
            chunk_start = chunk_end
        return CandleRead(start, end, tuple(pages))

    def _validated(self, venue: str, symbol: str, timeframe: str, start: int, end: int, limit: int) -> PageRequest:
        _text(venue, "venue")
        _text(symbol, "symbol")
        if type(timeframe) is not str or timeframe not in TIMEFRAME_MS:
            raise ValueError(f"timeframe must be one of {sorted(TIMEFRAME_MS)}, got {timeframe!r}")
        timeframe_ms = TIMEFRAME_MS[timeframe]
        require_instant(start, "start")
        require_instant(end, "end")
        if not _MIN_START_MS <= start <= _MAX_START_MS:
            raise ValueError(f"start must be within [{_MIN_START_MS}, {_MAX_START_MS}], got {start}")
        if end > _MAX_START_MS + timeframe_ms:
            raise ValueError(f"end must be at most {_MAX_START_MS + timeframe_ms}, got {end}")
        if start % timeframe_ms != 0 or end % timeframe_ms != 0:
            raise ValueError(f"start and end must be aligned to {timeframe_ms} ms, got {start} and {end}")
        if start >= end:
            raise ValueError(f"start must be before end, got {start} and {end}")
        if type(limit) is not int or not 1 <= limit <= MAX_PAGE_LIMIT:
            raise ValueError(f"limit must be an int from 1 to {MAX_PAGE_LIMIT}, got {limit!r}")
        return PageRequest(venue, symbol, timeframe, timeframe_ms, start, end, limit)

    def _get(self, url: str) -> tuple[int, bytes, str | None]:
        """`(status, body, Retry-After)` of one request, or `QuasarUnavailableError` when no complete response came."""
        deadline_at = time.monotonic() + self._deadline_s
        try:
            response = self._open(url)
            try:
                _check_deadline(deadline_at)
                body = _read_body(response, deadline_at)
                status = response.status
                if status is None:
                    raise QuasarUnavailableError("the response has no status")
                return status, body, response.headers.get("Retry-After")
            finally:
                response.close()
        except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException, OSError) as error:
            raise QuasarUnavailableError(
                f"no complete response from Quasar ({type(error).__name__}: {error})"
            ) from error

    def _open(self, url: str) -> _Response:
        try:
            return self._opener.open(url, timeout=self._timeout_s)  # type: ignore[no-any-return]
        except urllib.error.HTTPError as error:  # first: it is also a URLError and an OSError
            return error


def _check_deadline(deadline_at: float) -> None:
    if time.monotonic() > deadline_at:
        raise QuasarUnavailableError("the request outlived its deadline")


def _read_body(response: _Response, deadline_at: float) -> bytes:
    """The whole body, with the deadline checked before and after each read.

    `read1` returns what one socket read yields instead of waiting for a full chunk, so a server that drips bytes cannot
    keep a single call blocked past the deadline. It does not raise on a body cut short, so a body shorter than its
    `Content-Length` is reported here.
    """
    chunks: list[bytes] = []
    while True:
        _check_deadline(deadline_at)
        chunk = response.read1(_CHUNK_BYTES)
        _check_deadline(deadline_at)
        if not chunk:
            break
        chunks.append(chunk)
    body = b"".join(chunks)
    declared = response.headers.get("Content-Length")
    if declared is not None and declared.isascii() and declared.isdigit() and len(body) < int(declared):
        raise QuasarUnavailableError(f"the body is cut short: {len(body)} of {declared} bytes")
    return body
