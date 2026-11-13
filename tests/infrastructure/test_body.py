"""Errors, page types, the HTTP response value and the strict JSON body layer (SE-6 spec 5.3, 5.4 "Body", 5.5)."""

import dataclasses
import json
import sys
from collections.abc import Iterator
from decimal import Decimal
from functools import partial
from typing import NamedTuple

import pytest

from sentaris_engine.domain.errors import EvaluationTypeError
from sentaris_engine.infrastructure.quasar import (
    CandlePage,
    FundingRatePage,
    HttpResponse,
    OpenInterestPage,
    QuasarClientError,
    QuasarProtocolError,
    QuasarResponseError,
    QuasarTransportError,
    SeriesBounds,
    body,
)
from sentaris_engine.infrastructure.quasar.body import JsonFraction, decode_ok_body, error_fields, parse_json
from tests.domain.evaluation_helpers import raises_exactly
from tests.domain.row_builders import candle, funding, open_interest

JSON = "application/json"

# Contract section 2, the example error body.
CONTRACT_ERROR_BODY = (
    b'{"error": {"code": "invalid_parameter", "message": "limit must be between 1 and 1000",'
    b' "details": {"parameter": "limit", "received": "5000"}}}'
)

# Contract 5.2, the example body, with `coverage` replaced by a value holding a fraction and one unknown field added.
CONTRACT_5_2_WITH_FRACTIONS = b"""{
  "venue": "binance-usdm",
  "symbol": "BTC/USDT:USDT",
  "timeframe": "5m",
  "start": 1792643400000,
  "end": 1792673400000,
  "series": {
    "oldest_open_time_ms": 1792643400000,
    "newest_open_time_ms": 1792673100000
  },
  "candles": [
    {
      "open_time_ms": 1792643400000,
      "open": "82855.4",
      "high": "82866.1",
      "low": "82768.1",
      "close": "82768.2",
      "volume": "369.221",
      "turnover": "30587379.8759",
      "conflicted": false
    },
    {
      "open_time_ms": 1792643700000,
      "open": "82768.2",
      "high": "82768.2",
      "low": "82664.7",
      "close": "82709",
      "volume": "580.95",
      "turnover": "48054366.2802",
      "conflicted": false
    },
    {
      "open_time_ms": 1792644000000,
      "open": "82709.1",
      "high": "82765.3",
      "low": "82686.2",
      "close": "82744.5",
      "volume": "380.864",
      "turnover": "31506256.9708",
      "conflicted": false
    }
  ],
  "next": 1792644300000,
  "coverage": {"x": [{"y": 0.5}]},
  "z": -1.25E-3
}"""


# --- errors (spec 5.5) -----------------------------------------------------------------------------------------------


def test_error_classes() -> None:
    kinds = (QuasarTransportError, QuasarResponseError, QuasarProtocolError)
    assert len(set(kinds)) == 3
    for kind in kinds:
        assert kind.__bases__ == (QuasarClientError,)
    assert QuasarClientError.__bases__ == (Exception,)
    assert not issubclass(QuasarClientError, EvaluationTypeError)
    error = QuasarResponseError(503, "not_ready", "database_missing")
    assert (error.status, error.code, error.reason) == (503, "not_ready", "database_missing")


# --- page types (spec 5.3) -------------------------------------------------------------------------------------------

BOUNDS = SeriesBounds(10, 20)


def _candle_page(**overrides: object) -> CandlePage:
    valid = CandlePage(start=0, end=100, series=BOUNDS, rows=(candle(10), candle(20)), next=None)
    return dataclasses.replace(valid, **overrides)  # type: ignore[arg-type]


def test_page_types_are_validated_final_and_frozen() -> None:
    raises_exactly(TypeError, lambda: SeriesBounds(True, 1))
    raises_exactly(TypeError, lambda: SeriesBounds(1.0, 2))  # type: ignore[arg-type]
    raises_exactly(ValueError, lambda: SeriesBounds(-1, 0))
    raises_exactly(ValueError, lambda: SeriesBounds(0, 2**53))
    raises_exactly(ValueError, lambda: SeriesBounds(5, 4))

    raises_exactly(TypeError, lambda: _candle_page(rows=[candle(10)]))
    raises_exactly(TypeError, lambda: _candle_page(rows=(candle(10), open_interest(20))))
    raises_exactly(TypeError, lambda: _candle_page(series=None))
    raises_exactly(TypeError, lambda: _candle_page(next=True))
    raises_exactly(TypeError, lambda: _candle_page(start="1"))
    raises_exactly(ValueError, lambda: _candle_page(next=-1))

    oi_page = OpenInterestPage(start=0, end=100, series=BOUNDS, rows=(open_interest(10),), next=50)
    raises_exactly(TypeError, lambda: dataclasses.replace(oi_page, rows=(candle(10),)))  # type: ignore[arg-type]
    raises_exactly(TypeError, lambda: dataclasses.replace(oi_page, series=None))  # type: ignore[arg-type]
    funding_page = FundingRatePage(start=0, end_inclusive=100, series=None, rows=(), next=None)
    assert funding_page.series is None
    raises_exactly(TypeError, lambda: dataclasses.replace(funding_page, rows=(funding(10), candle(20))))  # type: ignore[arg-type]

    page = _candle_page()
    for kind in (SeriesBounds, CandlePage, OpenInterestPage, FundingRatePage):
        raises_exactly(TypeError, partial(type, "Sub", (kind,), {}))
    with pytest.raises(dataclasses.FrozenInstanceError):
        page.next = 5  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        BOUNDS.oldest = 1  # type: ignore[misc]
    assert _candle_page() == page
    assert SeriesBounds(10, 20) == BOUNDS
    assert FundingRatePage(0, 100, None, (), None) == funding_page


# --- HttpResponse (R8) -----------------------------------------------------------------------------------------------


def test_http_response_is_validated() -> None:
    raises_exactly(TypeError, lambda: HttpResponse("200", JSON, b""))  # type: ignore[arg-type]
    raises_exactly(TypeError, lambda: HttpResponse(True, JSON, b""))
    raises_exactly(TypeError, lambda: HttpResponse(200, b"x", b""))  # type: ignore[arg-type]
    raises_exactly(TypeError, lambda: HttpResponse(200, JSON, bytearray(b"")))  # type: ignore[arg-type]
    raises_exactly(TypeError, lambda: HttpResponse(200, JSON, "x"))  # type: ignore[arg-type]
    response = HttpResponse(200, None, b"")
    assert (response.status, response.content_type, response.body) == (200, None, b"")


# --- no float (DR-11) ------------------------------------------------------------------------------------------------


def _leaves(tree: object) -> Iterator[object]:
    """Every value of a parsed JSON tree, at every depth."""
    yield tree
    if type(tree) is dict:
        for value in tree.values():
            yield from _leaves(value)
    elif type(tree) is list:
        for item in tree:
            yield from _leaves(item)


def test_json_number_with_fraction_becomes_marker() -> None:
    tree = parse_json(b'{"a": 82709.5, "b": 8.27E4, "c": [1e3]}')
    assert type(tree) is dict
    values = (tree["a"], tree["b"], tree["c"][0])
    assert all(type(value) is JsonFraction for value in values)
    assert [value.text for value in values] == ["82709.5", "8.27E4", "1e3"]
    for other in (int, str, float, Decimal):
        assert not issubclass(JsonFraction, other)


def test_no_float_is_built_for_ignored_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    leaves = list(_leaves(parse_json(CONTRACT_5_2_WITH_FRACTIONS)))
    assert not any(isinstance(leaf, float) for leaf in leaves)
    fractions = [leaf for leaf in leaves if type(leaf) is JsonFraction]
    assert sorted(fraction.text for fraction in fractions) == ["-1.25E-3", "0.5"]

    monkeypatch.setattr(body, "_parse_float", float)
    assert any(isinstance(leaf, float) for leaf in _leaves(parse_json(CONTRACT_5_2_WITH_FRACTIONS)))


# --- parse failures (spec 5.4 exception table) -----------------------------------------------------------------------


class ParseFailure(NamedTuple):
    raw: bytes
    cause: type[BaseException]


PARSE_FAILURE_CASES: dict[str, ParseFailure] = {
    "invalid-utf8": ParseFailure(b'{"a":"\xff"}', UnicodeDecodeError),
    "malformed": ParseFailure(b"{", json.JSONDecodeError),
    "empty": ParseFailure(b"", json.JSONDecodeError),
    "trailing-data": ParseFailure(b"{} {}", json.JSONDecodeError),
    "bom": ParseFailure(b"\xef\xbb\xbf{}", json.JSONDecodeError),
    "deep-nesting": ParseFailure(b"[" * 200_000, RecursionError),
    "nan": ParseFailure(b'{"a": NaN}', body._JsonRefused),
    "infinity": ParseFailure(b'{"a": [Infinity]}', body._JsonRefused),
    "minus-infinity": ParseFailure(b'{"a": -Infinity}', body._JsonRefused),
    "duplicate-key": ParseFailure(b'{"a": 1, "a": 1}', body._JsonRefused),
    "nested-duplicate-key": ParseFailure(b'{"x": {"b": 1, "b": 2}}', body._JsonRefused),
    "oversized-integer": ParseFailure(b'{"a": ' + b"1" * 5000 + b"}", body._JsonRefused),
}


@pytest.fixture
def int_digit_limit() -> Iterator[None]:
    """Pin Python's integer-string digit limit to its default, so the oversized case does not depend on the
    environment (spec 5.4 uses Python's limit; a known limitation of the slice)."""
    previous = sys.get_int_max_str_digits()
    sys.set_int_max_str_digits(4300)
    try:
        yield
    finally:
        sys.set_int_max_str_digits(previous)


def _assert_protocol_error(case: ParseFailure) -> None:
    with pytest.raises(QuasarProtocolError) as info:
        decode_ok_body(JSON, case.raw)
    assert type(info.value) is QuasarProtocolError
    assert type(info.value.__cause__) is case.cause


@pytest.mark.usefixtures("int_digit_limit")
@pytest.mark.parametrize("case", PARSE_FAILURE_CASES.values(), ids=PARSE_FAILURE_CASES.keys())
def test_parse_failures_are_protocol_errors(case: ParseFailure) -> None:
    _assert_protocol_error(case)


def test_invalid_utf8_body_is_refused() -> None:
    _assert_protocol_error(PARSE_FAILURE_CASES["invalid-utf8"])


@pytest.mark.usefixtures("int_digit_limit")
@pytest.mark.parametrize("name", ["oversized-integer", "deep-nesting"])
def test_oversized_integer_and_deep_nesting_are_protocol_errors(name: str) -> None:
    _assert_protocol_error(PARSE_FAILURE_CASES[name])


@pytest.mark.parametrize("encoding", ["utf-16", "utf-32"])
def test_utf16_body_is_refused(encoding: str) -> None:
    raises_exactly(QuasarProtocolError, lambda: decode_ok_body(JSON, "{}".encode(encoding)))


@pytest.mark.parametrize("raw", [b"[]", b'"x"', b"1", b"null"])
def test_top_level_not_object_is_refused(raw: bytes) -> None:
    with pytest.raises(QuasarProtocolError) as info:
        decode_ok_body(JSON, raw)
    assert type(info.value) is QuasarProtocolError
    assert info.value.__cause__ is None


# --- Content-Type (R6) -----------------------------------------------------------------------------------------------


@pytest.mark.parametrize("content_type", [None, "text/plain", ""])
def test_non_json_content_type_is_refused(content_type: str | None) -> None:
    raises_exactly(QuasarProtocolError, lambda: decode_ok_body(content_type, b"{}"))


def test_non_utf8_charset_is_refused() -> None:
    raises_exactly(QuasarProtocolError, lambda: decode_ok_body("application/json; charset=latin-1", b"{}"))


ACCEPTED_CONTENT_TYPES = [
    "application/json",
    'Application/JSON; Charset="UTF-8"',
    "application/json;charset=utf-8",
    "application/json ; foo=bar",
    "application/json;",
]
REFUSED_CONTENT_TYPES = [
    "application/jsonx",
    "application/json-seq",
    "text/json",
    "application/json; charset=latin-1",
    "application/json; charset=utf-8; charset=latin-1",
]


def test_content_type_spellings() -> None:
    for content_type in ACCEPTED_CONTENT_TYPES:
        assert decode_ok_body(content_type, b'{"a": 1}') == {"a": 1}, content_type
    for content_type in REFUSED_CONTENT_TYPES:
        raises_exactly(QuasarProtocolError, partial(decode_ok_body, content_type, b"{}"))


# --- hooks (R3) ------------------------------------------------------------------------------------------------------


def _raise_runtime_error(*args: object) -> object:
    raise RuntimeError("hook bug")


HOOK_BODIES: dict[str, bytes] = {
    "_parse_constant": b'{"a": NaN}',
    "_object_pairs": b"{}",
    "_parse_int": b'{"a": 1}',
    "_parse_float": b'{"a": 1.5}',
}


@pytest.mark.parametrize("entry", ["decode_ok_body", "error_fields"])
@pytest.mark.parametrize("hook", HOOK_BODIES.keys())
def test_hook_programming_error_propagates(hook: str, entry: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(body, hook, _raise_runtime_error)
    raw = HOOK_BODIES[hook]
    if entry == "decode_ok_body":
        raises_exactly(RuntimeError, lambda: decode_ok_body(JSON, raw))
    else:
        raises_exactly(RuntimeError, lambda: error_fields(500, raw))


# --- the error predicate (spec 5.5) ----------------------------------------------------------------------------------


def _error(error: str) -> bytes:
    return b'{"error": ' + error.encode() + b"}"


ERROR_BODY_CASES: dict[str, tuple[int, bytes, tuple[str | None, str | None]]] = {
    "contract-400": (400, CONTRACT_ERROR_BODY, ("invalid_parameter", None)),
    "not-ready-reason": (
        503,
        b'{"error":{"code":"not_ready","message":"m","details":{"reason":"database_missing"}}}',
        ("not_ready", "database_missing"),
    ),
    "non-json": (500, b"<html>Bad Gateway</html>", (None, None)),
    "empty": (500, b"", (None, None)),
    "invalid-utf8": (500, b'{"error": {"code": "\xff"}}', (None, None)),
    "nan": (500, b'{"error": {"code": "internal_error", "x": NaN}}', (None, None)),
    "duplicate-key": (500, b'{"error": {"code": "internal_error", "code": "x"}}', (None, None)),
    "top-level-array": (500, b'[{"error": {"code": "internal_error"}}]', (None, None)),
    "no-error": (500, b'{"code": "internal_error"}', (None, None)),
    "error-not-object": (500, b'{"error": "internal_error"}', (None, None)),
    "code-int": (500, _error('{"code": 1}'), (None, None)),
    "code-empty": (500, _error('{"code": ""}'), (None, None)),
    "code-null": (500, _error('{"code": null}'), (None, None)),
    "code-missing": (500, _error('{"message": "m"}'), (None, None)),
    "not-ready-no-details": (503, _error('{"code": "not_ready"}'), ("not_ready", None)),
    "not-ready-details-array": (503, _error('{"code": "not_ready", "details": []}'), ("not_ready", None)),
    "not-ready-reason-int": (503, _error('{"code": "not_ready", "details": {"reason": 1}}'), ("not_ready", None)),
    "reason-on-500": (
        500,
        _error('{"code": "not_ready", "details": {"reason": "database_missing"}}'),
        ("not_ready", None),
    ),
    "reason-on-other-code": (
        503,
        _error('{"code": "other", "details": {"reason": "database_missing"}}'),
        ("other", None),
    ),
}


@pytest.mark.parametrize("case", ERROR_BODY_CASES.values(), ids=ERROR_BODY_CASES.keys())
def test_error_body_shapes(case: tuple[int, bytes, tuple[str | None, str | None]]) -> None:
    status, raw, expected = case
    assert error_fields(status, raw) == expected
