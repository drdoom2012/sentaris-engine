"""The single-page decoders: one `200` response into one page (SE-6 spec 5.4 "Echoed fields", "Series", "Rows",
"Order and window", "`next`"). The decoders do not look at `status` (R9); every violation is a
`QuasarProtocolError`."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Final, Literal, assert_never, final

from sentaris_engine.domain.errors import EvaluationTypeError
from sentaris_engine.domain.rows import Candle, FundingRate, OpenInterest
from sentaris_engine.domain.timing import MAX_TIME_MS
from sentaris_engine.infrastructure.quasar.body import decode_ok_body
from sentaris_engine.infrastructure.quasar.errors import QuasarProtocolError
from sentaris_engine.infrastructure.quasar.pages import CandlePage, FundingRatePage, OpenInterestPage, SeriesBounds
from sentaris_engine.infrastructure.quasar.transport import HttpResponse

# Contract section 1, "Decimals"; `fullmatch` with the ASCII class `[0-9]` (spec 5.4, review MEDIUM-1).
_UNSIGNED: Final = re.compile(r"(0|[1-9][0-9]*)(\.[0-9]*[1-9])?")

# Contract 6.7.3: `Regular` before `Special` at one `funding_time_ms`; the index is the sort rank.
_RATE_TYPES: Final = ("Regular", "Special")

# The server default of `limit` (contract 5.1, 6.5.2, 6.7.2).
_DEFAULT_LIMIT: Final = 1000

_MISSING: Final = object()

type _Kind = Literal["unsigned", "unsigned_or_null", "signed", "bool", "rate_type"]


@final
@dataclass(frozen=True, slots=True)
class _Shape:
    """What differs between the three endpoints (spec 5.4). It binds no row class: the decoders pass it per call."""

    series_field: str | None  # `timeframe` or `period`; none for funding
    time_semantics: str | None
    oldest: str
    newest: str
    rows_key: str
    time_key: str
    fields: tuple[tuple[str, _Kind], ...]  # after the time, in the order of the row constructor's parameters
    rank_key: str | None  # the second part of the sort key (contract 6.7.3)
    inclusive_end: bool  # contract 6.7.2, decision FA1


_CANDLES: Final = _Shape(
    series_field="timeframe",
    time_semantics=None,
    oldest="oldest_open_time_ms",
    newest="newest_open_time_ms",
    rows_key="candles",
    time_key="open_time_ms",
    fields=(
        ("open", "unsigned"),
        ("high", "unsigned"),
        ("low", "unsigned"),
        ("close", "unsigned"),
        ("volume", "unsigned"),
        ("turnover", "unsigned_or_null"),
        ("conflicted", "bool"),
    ),
    rank_key=None,
    inclusive_end=False,
)

_OPEN_INTEREST: Final = _Shape(
    series_field="period",
    time_semantics="period_end",
    oldest="oldest_time_ms",
    newest="newest_time_ms",
    rows_key="rows",
    time_key="time_ms",
    fields=(
        ("open_interest", "unsigned"),
        ("open_interest_value", "unsigned"),
        ("conflicted", "bool"),
    ),
    rank_key=None,
    inclusive_end=False,
)

_FUNDING: Final = _Shape(
    series_field=None,
    time_semantics="settlement",
    oldest="oldest_funding_time_ms",
    newest="newest_funding_time_ms",
    rows_key="rows",
    time_key="funding_time_ms",
    fields=(
        ("rate_type", "rate_type"),
        ("funding_rate", "signed"),
        ("mark_price", "unsigned_or_null"),
        ("conflicted", "bool"),
    ),
    rank_key="rate_type",
    inclusive_end=True,
)


def _field(tree: dict[str, object], key: str) -> object:
    value = tree.get(key, _MISSING)
    if value is _MISSING:
        raise QuasarProtocolError(f"{key} is missing (DR-15)")
    return value


def _instant(key: str, value: object) -> int:
    # The `check_instant` predicate, raising `QuasarProtocolError` directly (R5).
    if type(value) is not int or not 0 <= value <= MAX_TIME_MS:
        raise QuasarProtocolError(f"{key} is not a JSON integer in 0 … MAX_TIME_MS (R5)")
    return value


def _unsigned(key: str, value: object) -> Decimal:
    if type(value) is not str or _UNSIGNED.fullmatch(value) is None:
        raise QuasarProtocolError(f"{key} is not an unsigned decimal string in canonical form (DR-11)")
    return Decimal(value)


def _signed(key: str, value: object) -> Decimal:
    if type(value) is not str:
        raise QuasarProtocolError(f"{key} is not a signed decimal string (DR-11)")
    magnitude = value.removeprefix("-")
    if _UNSIGNED.fullmatch(magnitude) is None or (magnitude != value and magnitude == "0"):
        raise QuasarProtocolError(f"{key} is not a signed decimal string in canonical form (DR-11, contract 6.7.1)")
    return Decimal(value)


def _value(key: str, kind: _Kind, value: object) -> object:
    if kind == "unsigned":
        return _unsigned(key, value)
    if kind == "unsigned_or_null":
        return None if value is None else _unsigned(key, value)
    if kind == "signed":
        return _signed(key, value)
    if kind == "bool":
        if type(value) is not bool:
            raise QuasarProtocolError(f"{key} is not a JSON boolean")
        return value
    if kind == "rate_type":
        if type(value) is not str or value not in _RATE_TYPES:
            raise QuasarProtocolError(f"{key} is not exactly Regular or Special")
        return value
    assert_never(kind)


def _top(
    response: HttpResponse, shape: _Shape, venue: str, symbol: str, series_id: str | None, start: int, end: int
) -> dict[str, object]:
    """The body's top-level object, with every echoed field checked (spec 5.4 "Echoed fields")."""
    top = decode_ok_body(response.content_type, response.body)
    identifiers: list[tuple[str, str | None]] = [("venue", venue), ("symbol", symbol)]
    if shape.series_field is not None:
        identifiers.append((shape.series_field, series_id))
    for key, expected in identifiers:
        echoed = _field(top, key)
        if type(echoed) is not str or echoed != expected:
            raise QuasarProtocolError(f"{key} does not echo the request")
    if shape.time_semantics is not None:
        semantics = _field(top, "time_semantics")
        if type(semantics) is not str or semantics != shape.time_semantics:
            raise QuasarProtocolError("time_semantics is not the one of the row type (DR-24)")
    for key, expected_time in (("start", start), ("end", end)):
        echoed = _field(top, key)
        if type(echoed) is not int or echoed != expected_time:
            raise QuasarProtocolError(f"{key} does not echo the request")
    return top


def _series_object(top: dict[str, object], shape: _Shape) -> tuple[object, object]:
    series = _field(top, "series")
    if type(series) is not dict:
        raise QuasarProtocolError("series is not an object")
    return _field(series, shape.oldest), _field(series, shape.newest)


def _bounds(shape: _Shape, oldest: object, newest: object) -> SeriesBounds:
    oldest_ms = _instant(shape.oldest, oldest)
    newest_ms = _instant(shape.newest, newest)
    if oldest_ms > newest_ms:
        raise QuasarProtocolError("series bounds are inverted")
    return SeriesBounds(oldest_ms, newest_ms)


def _series(top: dict[str, object], shape: _Shape) -> SeriesBounds:
    return _bounds(shape, *_series_object(top, shape))


def _nullable_series(top: dict[str, object], shape: _Shape) -> SeriesBounds | None:
    oldest, newest = _series_object(top, shape)
    if oldest is None and newest is None:  # both together only (contract 6.7.4, decision FA4)
        return None
    return _bounds(shape, oldest, newest)


def _in_window(shape: _Shape, time: int, start: int, end: int) -> bool:
    return start <= time <= end if shape.inclusive_end else start <= time < end


def _rows_and_next[R](
    top: dict[str, object], shape: _Shape, row_class: Callable[..., R], start: int, end: int, limit: int | None
) -> tuple[tuple[R, ...], int | None]:
    """The rows (spec 5.4 "Rows", "Order and window") and `next` (spec 5.4 "`next`") of one page."""
    raw_rows = _field(top, shape.rows_key)
    if type(raw_rows) is not list:
        raise QuasarProtocolError(f"{shape.rows_key} is not an array")
    if len(raw_rows) > (_DEFAULT_LIMIT if limit is None else limit):
        raise QuasarProtocolError("more rows than limit (contract 3)")
    rows: list[R] = []
    previous: tuple[int, int] | None = None
    for raw in raw_rows:
        if type(raw) is not dict:
            raise QuasarProtocolError("a row is not an object")
        time = _instant(shape.time_key, _field(raw, shape.time_key))
        values = [_value(key, kind, _field(raw, key)) for key, kind in shape.fields]
        if not _in_window(shape, time, start, end):
            raise QuasarProtocolError("a row lies outside the request window")
        key = (time, 0 if shape.rank_key is None else _RATE_TYPES.index(raw[shape.rank_key]))
        if previous is not None and key <= previous:
            raise QuasarProtocolError("rows are not strictly ascending (contract 5.2, 6.5.4, 6.7.3)")
        previous = key
        try:
            row = row_class(time, *values)
        except EvaluationTypeError as exc:  # the only translation on the parsed tree (spec 5.4)
            raise QuasarProtocolError("a row is refused by its SE-3 row type") from exc
        rows.append(row)

    next_value = _field(top, "next")
    if next_value is None:
        return tuple(rows), None
    next_ms = _instant("next", next_value)
    if previous is None:
        raise QuasarProtocolError("next is not null on a page without rows (contract 3)")
    if not (previous[0] < next_ms and _in_window(shape, next_ms, start, end)):
        raise QuasarProtocolError("next is not after the last row and inside the window (contract 3, 6.7.3)")
    return tuple(rows), next_ms


def decode_candle_page(
    response: HttpResponse, venue: str, symbol: str, timeframe: str, start: int, end: int, limit: int | None
) -> CandlePage:
    """One `GET /v1/candles` response; the window is `start <= open_time_ms < end`."""
    top = _top(response, _CANDLES, venue, symbol, timeframe, start, end)
    series = _series(top, _CANDLES)
    # The row class is read from the module globals at each call (Task 2 interfaces).
    rows, next_ms = _rows_and_next(top, _CANDLES, Candle, start, end, limit)
    return CandlePage(start, end, series, rows, next_ms)


def decode_open_interest_page(
    response: HttpResponse, venue: str, symbol: str, period: str, start: int, end: int, limit: int | None
) -> OpenInterestPage:
    """One `GET /v1/open-interest` response; the window is `start <= time_ms < end`."""
    top = _top(response, _OPEN_INTEREST, venue, symbol, period, start, end)
    series = _series(top, _OPEN_INTEREST)
    rows, next_ms = _rows_and_next(top, _OPEN_INTEREST, OpenInterest, start, end, limit)
    return OpenInterestPage(start, end, series, rows, next_ms)


def decode_funding_rate_page(
    response: HttpResponse, venue: str, symbol: str, start: int, end_inclusive: int, limit: int | None
) -> FundingRatePage:
    """One `GET /v1/funding-rates` response; the window is `start <= funding_time_ms <= end_inclusive`."""
    top = _top(response, _FUNDING, venue, symbol, None, start, end_inclusive)
    series = _nullable_series(top, _FUNDING)
    rows, next_ms = _rows_and_next(top, _FUNDING, FundingRate, start, end_inclusive, limit)
    return FundingRatePage(start, end_inclusive, series, rows, next_ms)
