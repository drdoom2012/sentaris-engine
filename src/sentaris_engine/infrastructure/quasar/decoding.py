"""Strict decoding of a `GET /v1/candles` response and of Quasar's error responses (contract sections 1 to 3, 5).

The decoder is fail-closed. A price or volume is built from the JSON string, never from a number and never through
`float` (DR-11); anything the contract says is never sent is rejected. Unknown response fields are ignored at every
level, a missing documented field or a wrong type is a `ContractViolationError` (contract section 1, "Compatibility").
Nothing is filled, interpolated or deduplicated (DR-15). `conflicted` and `coverage` are carried as Quasar stated them
and never interpreted (OD-7, DR-21); `coverage` must only agree with the request and with itself.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from decimal import Decimal
from typing import NoReturn, cast

from sentaris_engine.domain.market import Candle
from sentaris_engine.domain.timing import EpochMs, require_instant
from sentaris_engine.infrastructure.quasar.errors import (
    ContractViolationError,
    InvalidParameterError,
    NotReadyError,
    QuasarApiError,
    QuasarError,
    UnexpectedResponseError,
    UnknownSeriesError,
)
from sentaris_engine.infrastructure.quasar.pages import CandlePage, PageCoverage, PageRequest

_OK = 200
_API_STATUSES = frozenset({400, 404, 405, 500, 503})
_EXCERPT_CHARS = 200
# Contract section 1, "Decimals". `[0-9]`, never `\d` (which accepts other scripts), and `fullmatch`, never `$`.
_DECIMAL = re.compile(r"(0|[1-9][0-9]*)(\.[0-9]*[1-9])?")
_RETRY_AFTER = re.compile(r"[0-9]{1,6}")


def _excerpt(body: bytes) -> str:
    # 4 bytes per character is the most UTF-8 needs, so the first 800 bytes hold the first 200 characters.
    return body[: _EXCERPT_CHARS * 4].decode("utf-8", errors="replace")[:_EXCERPT_CHARS]


def _reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key {key!r}")
        result[key] = value
    return result


def _reject_constant(name: str) -> NoReturn:
    raise ValueError(f"{name} is not strict JSON")


def _parse_json_object(body: bytes, status: int) -> dict[str, object]:
    """The body as a strict-JSON object, else `UnexpectedResponseError` (the response is not a Quasar document)."""
    try:
        parsed = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=_reject_duplicates,
            parse_constant=_reject_constant,
        )
    except (ValueError, RecursionError) as error:
        raise UnexpectedResponseError(
            f"the body is not strict JSON ({type(error).__name__})", status, _excerpt(body)
        ) from None
    if type(parsed) is not dict:
        raise UnexpectedResponseError("the body is not a JSON object", status, _excerpt(body))
    return cast(dict[str, object], parsed)


def _violation(message: str) -> ContractViolationError:
    return ContractViolationError(message, _OK)


def _field(obj: dict[str, object], key: str, where: str) -> object:
    if key not in obj:
        raise _violation(f"{where}.{key} is missing")
    return obj[key]


def _str(obj: dict[str, object], key: str, where: str) -> str:
    value = _field(obj, key, where)
    if type(value) is not str:
        raise _violation(f"{where}.{key} must be a string, got {type(value).__name__}")
    return value


def _bool(obj: dict[str, object], key: str, where: str) -> bool:
    value = _field(obj, key, where)
    if type(value) is not bool:
        raise _violation(f"{where}.{key} must be a boolean, got {type(value).__name__}")
    return value


def _object(obj: dict[str, object], key: str, where: str) -> dict[str, object]:
    value = _field(obj, key, where)
    if type(value) is not dict:
        raise _violation(f"{where}.{key} must be an object, got {type(value).__name__}")
    return cast(dict[str, object], value)


def _list(obj: dict[str, object], key: str, where: str) -> list[object]:
    value = _field(obj, key, where)
    if type(value) is not list:
        raise _violation(f"{where}.{key} must be an array, got {type(value).__name__}")
    return cast(list[object], value)


def _instant_value(value: object, name: str) -> EpochMs:
    try:
        return require_instant(value, name)
    except ValueError as error:
        raise _violation(str(error)) from None


def _instant(obj: dict[str, object], key: str, where: str) -> EpochMs:
    return _instant_value(_field(obj, key, where), f"{where}.{key}")


def _count(obj: dict[str, object], key: str, where: str) -> int:
    value = _field(obj, key, where)
    if type(value) is not int:
        raise _violation(f"{where}.{key} must be an integer, got {type(value).__name__}")
    if value < 0:
        raise _violation(f"{where}.{key} must not be negative, got {value}")
    return value


def _decimal_text(value: object, name: str) -> Decimal:
    if type(value) is not str:
        raise _violation(f"{name} must be a decimal string, got {type(value).__name__}")
    if _DECIMAL.fullmatch(value) is None:
        raise _violation(f"{name} is not a canonical decimal string: {value[:64]!r}")
    return Decimal(value)


def _decimal(obj: dict[str, object], key: str, where: str) -> Decimal:
    return _decimal_text(_field(obj, key, where), f"{where}.{key}")


def _candle(value: object, index: int) -> Candle:
    where = f"candles[{index}]"
    if type(value) is not dict:
        raise _violation(f"{where} must be an object, got {type(value).__name__}")
    obj = cast(dict[str, object], value)
    turnover_value = _field(obj, "turnover", where)
    turnover = None if turnover_value is None else _decimal_text(turnover_value, f"{where}.turnover")
    try:
        return Candle(
            open_time_ms=_instant(obj, "open_time_ms", where),
            open=_decimal(obj, "open", where),
            high=_decimal(obj, "high", where),
            low=_decimal(obj, "low", where),
            close=_decimal(obj, "close", where),
            volume=_decimal(obj, "volume", where),
            turnover=turnover,
            conflicted=_bool(obj, "conflicted", where),
        )
    except ValueError as error:
        raise _violation(f"{where} is not a valid candle: {error}") from None


def _check_candles(candles: tuple[Candle, ...], request: PageRequest) -> None:
    if len(candles) > request.limit:
        raise _violation(f"the page holds {len(candles)} candles, more than the limit {request.limit}")
    previous: EpochMs | None = None
    for index, candle in enumerate(candles):
        time = candle.open_time_ms
        if not request.start <= time < request.end:
            raise _violation(
                f"candles[{index}].open_time_ms {time} is outside the window [{request.start}, {request.end})"
            )
        if time % request.timeframe_ms != 0:
            raise _violation(f"candles[{index}].open_time_ms {time} is not aligned to {request.timeframe_ms} ms")
        if previous is not None and time <= previous:
            raise _violation(f"candles are not strictly ascending: {time} follows {previous}")
        previous = time


def _check_next(next_start: EpochMs | None, candles: tuple[Candle, ...], request: PageRequest) -> None:
    if next_start is None:
        return
    if not candles:
        raise _violation("next must be null when no candle is returned")
    if len(candles) != request.limit:
        raise _violation(f"next is set on a page of {len(candles)} candles, fewer than the limit {request.limit}")
    if next_start <= candles[-1].open_time_ms:
        raise _violation(f"next {next_start} must be greater than the last candle {candles[-1].open_time_ms}")
    if next_start >= request.end:
        raise _violation(f"next {next_start} must be less than end {request.end}")
    if next_start % request.timeframe_ms != 0:
        raise _violation(f"next {next_start} is not aligned to {request.timeframe_ms} ms")


def _coverage(obj: dict[str, object], next_start: EpochMs | None, request: PageRequest) -> PageCoverage:
    where = "coverage"
    span = _object(obj, "span", where)
    coverage = PageCoverage(
        span_start=_instant(span, "start", "coverage.span"),
        span_end=_instant(span, "end", "coverage.span"),
        slots=_count(obj, "slots", where),
        present_slots=_count(obj, "present_slots", where),
        conflicted_slots=_count(obj, "conflicted_slots", where),
        unavailable_slots=_count(obj, "unavailable_slots", where),
        missing_slots=_count(obj, "missing_slots", where),
        beyond_stored_slots=_count(obj, "beyond_stored_slots", where),
        gap_free=_bool(obj, "gap_free", where),
    )
    if coverage.span_start != request.start:
        raise _violation(f"coverage span start {coverage.span_start} differs from start {request.start}")
    expected_end = request.end if next_start is None else next_start
    if coverage.span_end != expected_end:
        raise _violation(f"coverage span end {coverage.span_end} must be {expected_end}")
    span_ms = coverage.span_end - coverage.span_start
    if span_ms % request.timeframe_ms != 0 or span_ms // request.timeframe_ms != coverage.slots:
        raise _violation(f"coverage slots {coverage.slots} do not match the span of {span_ms} ms")
    states = (
        coverage.present_slots
        + coverage.conflicted_slots
        + coverage.unavailable_slots
        + coverage.missing_slots
        + coverage.beyond_stored_slots
    )
    if states != coverage.slots:
        raise _violation(f"coverage counts sum to {states}, not to slots {coverage.slots}")
    no_gap = (
        coverage.conflicted_slots == 0
        and coverage.unavailable_slots == 0
        and coverage.missing_slots == 0
        and coverage.beyond_stored_slots == 0
    )
    if coverage.gap_free != no_gap:
        raise _violation("coverage gap_free does not agree with its counts")
    return coverage


def decode_candle_page(body: bytes, request: PageRequest) -> CandlePage:
    """The `200` body of `GET /v1/candles` as a `CandlePage`, checked against `request` and against itself.

    A body that is not a strict-JSON object is `UnexpectedResponseError` (status 200); an object that is not a valid
    page (a missing field, a wrong type, a numeric or non-canonical decimal, an echo that differs from the request, a
    candle outside the window or out of order, a `next` that does not advance, an inconsistent `coverage`) is
    `ContractViolationError` (status 200).
    """
    obj = _parse_json_object(body, _OK)
    for key, expected in (("venue", request.venue), ("symbol", request.symbol), ("timeframe", request.timeframe)):
        echoed = _str(obj, key, "page")
        if echoed != expected:
            raise _violation(f"{key} {echoed!r} differs from the requested {expected!r}")
    start = _instant(obj, "start", "page")
    end = _instant(obj, "end", "page")
    if start != request.start or end != request.end:
        raise _violation(f"window [{start}, {end}) differs from the requested [{request.start}, {request.end})")
    series = _object(obj, "series", "page")
    oldest = _instant(series, "oldest_open_time_ms", "series")
    newest = _instant(series, "newest_open_time_ms", "series")
    raw_candles = _list(obj, "candles", "page")
    next_value = _field(obj, "next", "page")
    next_start = None if next_value is None else _instant_value(next_value, "page.next")
    coverage_obj = _object(obj, "coverage", "page")

    candles = tuple(_candle(item, index) for index, item in enumerate(raw_candles))
    _check_candles(candles, request)
    _check_next(next_start, candles, request)
    coverage = _coverage(coverage_obj, next_start, request)
    return CandlePage(
        start=start,
        end=end,
        oldest_open_time_ms=oldest,
        newest_open_time_ms=newest,
        candles=candles,
        next_start=next_start,
        coverage=coverage,
    )


def _error_fields(obj: dict[str, object]) -> tuple[str, str, dict[str, object]] | None:
    """`(code, message, details)` of a well-formed contract section 2 error body, else `None`."""
    error = obj.get("error")
    if type(error) is not dict:
        return None
    fields = cast(dict[str, object], error)
    code = fields.get("code")
    message = fields.get("message")
    details = fields.get("details")
    if type(code) is not str or type(message) is not str or type(details) is not dict:
        return None
    return code, message, cast(dict[str, object], details)


def decode_error(status: int, body: bytes, retry_after: str | None) -> QuasarError:
    """The exception for a non-`200` response, for the client to raise.

    `QuasarApiError` (or its subclass for `400 invalid_parameter`, `404 unknown_series`, `503 not_ready`) only when the
    status is one of 400, 404, 405, 500, 503 and the body is a well-formed contract section 2 error body. Anything
    else, a `200` included, cannot be attributed to the Quasar API and is `UnexpectedResponseError` with an excerpt.
    `Retry-After` counts only when it is 1 to 6 ASCII digits.
    """
    if status not in _API_STATUSES:
        return UnexpectedResponseError(f"unexpected HTTP status {status}", status, _excerpt(body))
    try:
        obj = _parse_json_object(body, status)
    except UnexpectedResponseError as error:
        return error
    fields = _error_fields(obj)
    if fields is None:
        return UnexpectedResponseError(f"HTTP {status} without a Quasar error body", status, _excerpt(body))
    code, message, details = fields
    constructors: dict[tuple[int, str], Callable[[], QuasarApiError]] = {
        (400, "invalid_parameter"): lambda: InvalidParameterError(status, code, message, details),
        (404, "unknown_series"): lambda: UnknownSeriesError(status, code, message, details),
        (503, "not_ready"): lambda: NotReadyError(status, code, message, details, _retry_after_s(retry_after)),
    }
    build = constructors.get((status, code))
    return build() if build is not None else QuasarApiError(status, code, message, details)


def _retry_after_s(value: str | None) -> int | None:
    if value is None or _RETRY_AFTER.fullmatch(value) is None:
        return None
    return int(value)
