"""The Quasar REST client (SE-6 spec 5.1, 5.2, 5.5): arguments, request URLs, paging and status mapping over an
injected or default transport. Quasar is reached only through its REST API (DR-18, DR-19)."""

from collections.abc import Callable
from typing import Final, final
from urllib.parse import quote, urlsplit

from sentaris_engine.domain.timing import check_duration, check_instant
from sentaris_engine.infrastructure.quasar import transport as transports
from sentaris_engine.infrastructure.quasar.body import error_fields
from sentaris_engine.infrastructure.quasar.decoding import (
    decode_candle_page,
    decode_funding_rate_page,
    decode_open_interest_page,
)
from sentaris_engine.infrastructure.quasar.errors import QuasarResponseError
from sentaris_engine.infrastructure.quasar.pages import CandlePage, FundingRatePage, OpenInterestPage
from sentaris_engine.infrastructure.quasar.transport import HttpResponse, Transport

_CANDLES_PATH: Final = "/v1/candles"
_OPEN_INTEREST_PATH: Final = "/v1/open-interest"
_FUNDING_RATES_PATH: Final = "/v1/funding-rates"


def _identifier(value: object) -> str:
    """An exact non-empty `str` that encodes as UTF-8 (spec 5.2; R4)."""
    if type(value) is not str:
        raise TypeError("identifier is not an exact str")
    if value == "":
        raise ValueError("identifier is empty")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError("identifier cannot be encoded as UTF-8") from None
    return value


def _limit(value: object) -> int | None:
    if value is None:
        return None
    if type(value) is not int:
        raise TypeError("limit is not an exact int or None")
    if value < 1:
        raise ValueError("limit is below 1")
    return value


def _base(value: object) -> str:
    """The normalised base URL (spec 5.1; R7)."""
    if type(value) is not str:
        raise TypeError("base_url is not an exact str")
    if not value or any(not "!" <= char <= "~" for char in value):
        raise ValueError("base_url holds a character outside ! to ~")
    if any(char in value for char in "?#;"):
        raise ValueError("base_url holds a query, fragment or params")
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https"):
        raise ValueError("base_url is not an http or https URL")
    if not parts.hostname:
        raise ValueError("base_url has no host")
    if "@" in parts.netloc:
        raise ValueError("base_url holds userinfo")
    _ = parts.port  # reading it is what validates the port (R7)
    return f"{parts.scheme}://{parts.netloc}{parts.path.rstrip('/')}"


@final
class QuasarClient:
    """Reads a whole window of one series page by page; every read is a function of its arguments and the bytes
    the transport returns (DR-09). A failure on any page fails the read (spec 5.5)."""

    def __init__(self, base_url: str, timeout_ms: int, transport: Transport | None = None) -> None:
        self._base = _base(base_url)
        self._timeout_ms = check_duration(timeout_ms)
        if transport is None:
            self._transport: Transport = transports.urllib_transport
        elif callable(transport):
            self._transport = transport
        else:
            raise TypeError("transport is neither None nor callable")

    def read_candles(
        self, venue: str, symbol: str, timeframe: str, start: int, end: int, limit: int | None = None
    ) -> tuple[CandlePage, ...]:
        """`GET /v1/candles` over `start <= open_time_ms < end`."""
        series = [("venue", _identifier(venue)), ("symbol", _identifier(symbol)), ("timeframe", _identifier(timeframe))]
        checked_limit = _limit(limit)
        return self._read(
            _CANDLES_PATH,
            series,
            start,
            end,
            checked_limit,
            lambda response, cursor: decode_candle_page(response, venue, symbol, timeframe, cursor, end, checked_limit),
        )

    def read_open_interest(
        self, venue: str, symbol: str, period: str, start: int, end: int, limit: int | None = None
    ) -> tuple[OpenInterestPage, ...]:
        """`GET /v1/open-interest` over `start <= time_ms < end`."""
        series = [("venue", _identifier(venue)), ("symbol", _identifier(symbol)), ("period", _identifier(period))]
        checked_limit = _limit(limit)
        return self._read(
            _OPEN_INTEREST_PATH,
            series,
            start,
            end,
            checked_limit,
            lambda response, cursor: decode_open_interest_page(
                response, venue, symbol, period, cursor, end, checked_limit
            ),
        )

    def read_funding_rates(
        self, venue: str, symbol: str, start: int, end_inclusive: int, limit: int | None = None
    ) -> tuple[FundingRatePage, ...]:
        """`GET /v1/funding-rates` over `start <= funding_time_ms <= end_inclusive`."""
        series = [("venue", _identifier(venue)), ("symbol", _identifier(symbol))]
        checked_limit = _limit(limit)
        return self._read(
            _FUNDING_RATES_PATH,
            series,
            start,
            end_inclusive,
            checked_limit,
            lambda response, cursor: decode_funding_rate_page(
                response, venue, symbol, cursor, end_inclusive, checked_limit
            ),
        )

    def _read[P: (CandlePage, OpenInterestPage, FundingRatePage)](
        self,
        path: str,
        series: list[tuple[str, str]],
        start: int,
        end: int,
        limit: int | None,
        decode: Callable[[HttpResponse, int], P],
    ) -> tuple[P, ...]:
        """The page loop of spec 5.2: the first request uses the caller's `start`, each further one the previous
        page's `next`, all with the caller's `end`."""
        cursor = check_instant(start)
        window_end = check_instant(end)
        pages: list[P] = []
        while True:
            params = [*series, ("start", str(cursor)), ("end", str(window_end))]
            if limit is not None:
                params.append(("limit", str(limit)))
            query = "&".join(f"{name}={quote(value, safe='/:')}" for name, value in params)
            response = self._transport(f"{self._base}{path}?{query}", self._timeout_ms)
            if type(response) is not HttpResponse:
                raise TypeError("the transport did not return an HttpResponse (R8)")
            if response.status != 200:
                raise QuasarResponseError(response.status, *error_fields(response.status, response.body))
            page = decode(response, cursor)
            pages.append(page)
            if page.next is None:
                return tuple(pages)
            cursor = page.next
