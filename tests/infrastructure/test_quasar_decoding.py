import copy
import json
from dataclasses import replace
from decimal import Decimal
from typing import Any, cast

import pytest

from sentaris_engine.infrastructure.quasar.decoding import decode_candle_page, decode_error
from sentaris_engine.infrastructure.quasar.errors import (
    ContractViolationError,
    InvalidParameterError,
    NotReadyError,
    QuasarApiError,
    QuasarError,
    QuasarUnavailableError,
    UnexpectedResponseError,
    UnknownSeriesError,
)
from sentaris_engine.infrastructure.quasar.pages import CandlePage, PageCoverage, PageRequest
from tests.support.quasar_fixtures import (
    EXAMPLE_BODY,
    EXAMPLE_REQUEST,
    FIVE_MINUTES,
    candle_json,
    encode,
    error_body,
    page_json,
)

START = EXAMPLE_REQUEST.start
END = EXAMPLE_REQUEST.end
PRICE_FIELDS = ("open", "high", "low", "close", "volume", "turnover")


def decode(obj: object, request: PageRequest = EXAMPLE_REQUEST) -> CandlePage:
    return decode_candle_page(encode(obj), request)


def example() -> dict[str, Any]:
    loaded = json.loads(EXAMPLE_BODY)
    assert isinstance(loaded, dict)
    return cast(dict[str, Any], loaded)


def request_with(limit: int) -> PageRequest:
    return replace(EXAMPLE_REQUEST, limit=limit)


def slot(index: int) -> int:
    return START + index * FIVE_MINUTES


def delete_path(obj: dict[str, Any], path: tuple[str | int, ...]) -> dict[str, Any]:
    result = copy.deepcopy(obj)
    target: Any = result
    for step in path[:-1]:
        target = target[step]
    del target[path[-1]]
    return result


def set_path(obj: dict[str, Any], path: tuple[str | int, ...], value: object) -> dict[str, Any]:
    result = copy.deepcopy(obj)
    target: Any = result
    for step in path[:-1]:
        target = target[step]
    target[path[-1]] = value
    return result


def test_contract_example_decodes_exactly() -> None:
    page = decode_candle_page(EXAMPLE_BODY, EXAMPLE_REQUEST)

    assert [candle.open_time_ms for candle in page.candles] == [1792643400000, 1792643700000, 1792644000000]
    assert [candle.close for candle in page.candles] == [Decimal("82768.2"), Decimal(82709), Decimal("82744.5")]
    assert page.candles[1].close.as_tuple().exponent == 0
    assert page.candles[0].turnover is not None
    assert page.candles[0].turnover.as_tuple().exponent == -4
    assert [candle.turnover for candle in page.candles] == [
        Decimal("30587379.8759"),
        Decimal("48054366.2802"),
        Decimal("31506256.9708"),
    ]
    assert [candle.conflicted for candle in page.candles] == [False, False, False]
    assert page.start == START
    assert page.end == END
    assert page.next_start == 1792644300000
    assert page.oldest_open_time_ms == 1792643400000
    assert page.newest_open_time_ms == 1792673100000
    assert page.coverage == PageCoverage(1792643400000, 1792644300000, 3, 3, 0, 0, 0, 0, True)


def test_unknown_fields_are_ignored() -> None:
    expected = decode_candle_page(EXAMPLE_BODY, EXAMPLE_REQUEST)
    body = example()
    body["extra_float"] = 1.5
    body["extra_object"] = {"a": [1, 2.5, {"b": None}]}
    body["extra_list"] = [1.5, "x"]
    body["series"]["extra"] = 0.25
    body["coverage"]["extra"] = {"x": 1}
    body["coverage"]["span"]["extra"] = [1.5]
    body["candles"][0]["extra"] = 2.5
    body["candles"][1]["extra"] = {"k": "v"}
    body["candles"][2]["extra"] = [1.5]

    assert decode(body) == expected


def test_turnover_null_is_kept_and_absent_turnover_is_rejected() -> None:
    body = set_path(example(), ("candles", 0, "turnover"), None)
    assert decode(body).candles[0].turnover is None

    with pytest.raises(ContractViolationError):
        decode(delete_path(example(), ("candles", 0, "turnover")))


def test_conflicted_candle_is_returned_and_flagged() -> None:
    request = request_with(2)
    candles = [candle_json(slot(0)), candle_json(slot(1), conflicted=True, close="1.5")]
    page = decode(page_json(request, candles), request)

    assert len(page.candles) == 2
    assert page.candles[0].conflicted is False
    assert page.candles[1].conflicted is True
    assert page.candles[1].close == Decimal("1.5")
    assert page.coverage.conflicted_slots == 1


NUMERIC_PRICES: list[tuple[str, object]] = [
    (field, value)
    for field in PRICE_FIELDS
    for value in (82709, 82709.5, True, ["1"], None)
    if not (field == "turnover" and value is None)  # null is a legal turnover
]


@pytest.mark.parametrize(("field", "value"), NUMERIC_PRICES, ids=lambda item: repr(item))
def test_numeric_price_is_rejected(field: str, value: object) -> None:
    with pytest.raises(ContractViolationError):
        decode(set_path(example(), ("candles", 1, field), value))


@pytest.mark.parametrize("field", PRICE_FIELDS)
@pytest.mark.parametrize(
    "text",
    [
        "",
        " 1",
        "1 ",
        "1\n",
        "+1",
        "-1",
        "1e5",
        "1E5",
        "1.",
        ".5",
        "01",
        "00",
        "0.50",
        "82709.0",
        "1_000",
        "NaN",
        "Infinity",
        "-0",
        "١٢٣",
        "1,5",
    ],
)
def test_non_canonical_decimal_text_is_rejected(field: str, text: str) -> None:
    with pytest.raises(ContractViolationError):
        decode(set_path(example(), ("candles", 1, field), text))


@pytest.mark.parametrize("text", ["0", "0.5", "82709", "0.00000001", "123456789012345678901234567890.123456789"])
def test_canonical_decimal_text_is_accepted(text: str) -> None:
    page = decode(set_path(example(), ("candles", 1, "close"), text))

    assert page.candles[1].close.as_tuple() == Decimal(text).as_tuple()


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"not json",
        EXAMPLE_BODY[:120],
        b"<html></html>",
        b"[]",
        b"null",
        b'"x"',
        b"\xff\xfe{}",
        b'{"a": 1, "a": 2}',
        b'{"x": NaN}',
        b'{"x": Infinity}',
        b'{"x": -Infinity}',
        b"[" * 100000,
    ],
)
def test_bodies_that_are_not_a_json_object_are_unexpected_responses(body: bytes) -> None:
    with pytest.raises(UnexpectedResponseError) as caught:
        decode_candle_page(body, EXAMPLE_REQUEST)

    assert caught.value.status == 200
    assert (caught.value.excerpt == "") == (body == b"")
    assert len(caught.value.excerpt) <= 200


def test_empty_object_is_a_contract_violation_not_an_unexpected_response() -> None:
    with pytest.raises(ContractViolationError) as caught:
        decode({})

    assert caught.value.status == 200
    assert not isinstance(caught.value, UnexpectedResponseError)


DOCUMENTED_PATHS: list[tuple[str | int, ...]] = [
    ("venue",),
    ("symbol",),
    ("timeframe",),
    ("start",),
    ("end",),
    ("series",),
    ("series", "oldest_open_time_ms"),
    ("series", "newest_open_time_ms"),
    ("candles",),
    ("next",),
    ("coverage",),
    ("coverage", "span"),
    ("coverage", "span", "start"),
    ("coverage", "span", "end"),
    ("coverage", "slots"),
    ("coverage", "present_slots"),
    ("coverage", "conflicted_slots"),
    ("coverage", "unavailable_slots"),
    ("coverage", "missing_slots"),
    ("coverage", "beyond_stored_slots"),
    ("coverage", "gap_free"),
    *[("candles", 0, name) for name in ("open_time_ms", "open", "high", "low", "close", "volume", "turnover")],
    ("candles", 0, "conflicted"),
]


@pytest.mark.parametrize("path", DOCUMENTED_PATHS, ids=lambda path: ".".join(str(step) for step in path))
def test_missing_documented_field_is_rejected(path: tuple[str | int, ...]) -> None:
    with pytest.raises(ContractViolationError):
        decode(delete_path(example(), path))


MISTYPED: list[tuple[tuple[str | int, ...], object]] = [
    (("venue",), 1),
    (("symbol",), None),
    (("timeframe",), ["5m"]),
    (("start",), float(START)),
    (("end",), True),
    (("series",), []),
    (("series", "oldest_open_time_ms"), "1"),
    (("series", "newest_open_time_ms"), 1.5),
    (("candles",), {}),
    (("candles",), "x"),
    (("candles", 0), []),
    (("candles", 0), "x"),
    (("candles", 0, "open_time_ms"), float(START)),
    (("candles", 0, "open_time_ms"), True),
    (("candles", 0, "open_time_ms"), str(START)),
    (("candles", 0, "conflicted"), 0),
    (("candles", 0, "conflicted"), "false"),
    (("next",), float(slot(3))),
    (("next",), True),
    (("next",), str(slot(3))),
    (("coverage",), []),
    (("coverage", "span"), []),
    (("coverage", "span", "start"), float(START)),
    (("coverage", "span", "end"), str(slot(3))),
    (("coverage", "gap_free"), "true"),
    (("coverage", "gap_free"), 1),
    *[
        (("coverage", name), bad)
        for name in ("slots", "present_slots", "conflicted_slots", "unavailable_slots", "missing_slots")
        for bad in (1.5, True, -1)
    ],
    (("coverage", "beyond_stored_slots"), 1.5),
    (("coverage", "beyond_stored_slots"), True),
    (("coverage", "beyond_stored_slots"), -1),
]


@pytest.mark.parametrize(("path", "value"), MISTYPED, ids=lambda item: repr(item)[:40])
def test_mistyped_documented_field_is_rejected(path: tuple[str | int, ...], value: object) -> None:
    with pytest.raises(ContractViolationError):
        decode(set_path(example(), path, value))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("venue", "other"),
        ("symbol", "ETH/USDT:USDT"),
        ("timeframe", "1h"),
        ("start", START + FIVE_MINUTES),
        ("end", END + FIVE_MINUTES),
    ],
)
def test_echo_must_match_the_request(field: str, value: object) -> None:
    with pytest.raises(ContractViolationError):
        decode(set_path(example(), (field,), value))


@pytest.mark.parametrize(
    ("times", "limit", "keyword"),
    [
        ([START - FIVE_MINUTES, START], 10, "window"),
        ([END - FIVE_MINUTES, END], 10, "window"),
        ([START, START + 1], 10, "aligned"),
        ([slot(1), slot(0)], 10, "ascending"),
        ([slot(1), slot(1)], 10, "ascending"),
        ([slot(0), slot(1), slot(2)], 2, "limit"),
    ],
    ids=["before-start", "equal-end", "unaligned", "descending", "duplicate", "over-limit"],
)
def test_candles_must_lie_in_the_window_aligned_and_ascending(times: list[int], limit: int, keyword: str) -> None:
    request = request_with(limit)
    body = page_json(request, [candle_json(time) for time in times])

    with pytest.raises(ContractViolationError, match=keyword):
        decode(body, request)


def test_next_must_advance_inside_the_window() -> None:
    request = request_with(2)
    two = [candle_json(slot(0)), candle_json(slot(1))]

    assert decode(page_json(request, two), request).next_start is None
    assert decode(page_json(request, two, next_start=slot(5)), request).next_start == slot(5)

    rejected: list[tuple[list[dict[str, object]], int, str]] = [
        (two, slot(1), "next"),  # equal to the last candle
        (two, slot(0), "next"),  # less than it
        (two, END, "next"),  # equal to end
        (two, END + FIVE_MINUTES, "next"),  # greater than end
        (two, slot(1) + 1, "next"),  # unaligned
    ]
    for candles, next_start, keyword in rejected:
        with pytest.raises(ContractViolationError, match=keyword):
            decode(page_json(request, candles, next_start=next_start), request)

    empty = page_json(request, [], oldest=slot(0), newest=slot(0), next_start=slot(1))
    with pytest.raises(ContractViolationError, match="next"):
        decode(empty, request)

    request_three = request_with(3)
    short = page_json(request_three, two, next_start=slot(5))
    with pytest.raises(ContractViolationError, match="next"):
        decode(short, request_three)


def coverage_case(**changes: object) -> dict[str, Any]:
    """The example page (next not null, limit 3) with some coverage fields replaced."""
    body = example()
    for key, value in changes.items():
        if key == "span_start":
            body["coverage"]["span"]["start"] = value
        elif key == "span_end":
            body["coverage"]["span"]["end"] = value
        else:
            body["coverage"][key] = value
    return body


def test_coverage_must_be_consistent_with_the_request_and_itself() -> None:
    full_span = (END - START) // FIVE_MINUTES
    cases: dict[str, dict[str, Any]] = {  # the keys name the rule each case breaks
        "span start differs": coverage_case(span_start=START + FIVE_MINUTES, slots=2, present_slots=2),
        "span end is end while next is set": coverage_case(
            span_end=END, slots=full_span, missing_slots=full_span - 3, gap_free=False
        ),
        "slots do not match the span": coverage_case(slots=4, missing_slots=1, gap_free=False),
        "counts do not sum to slots": coverage_case(present_slots=2),
        "gap_free with missing": coverage_case(present_slots=2, missing_slots=1),
        "gap_free with conflicted": coverage_case(present_slots=2, conflicted_slots=1),
        "gap_free with unavailable": coverage_case(present_slots=2, unavailable_slots=1),
        "gap_free with beyond stored": coverage_case(present_slots=2, beyond_stored_slots=1),
        "gap_free false with all four zero": coverage_case(gap_free=False),
        "span not a multiple of the timeframe": coverage_case(span_end=1792644300001),
    }
    for body in cases.values():
        with pytest.raises(ContractViolationError, match="coverage"):
            decode(body)

    request = request_with(3)
    three = [candle_json(slot(0)), candle_json(slot(1)), candle_json(slot(2))]
    last_page = page_json(request, three)
    assert decode(last_page, request).coverage.span_end == END
    shortened = set_path(cast(dict[str, Any], last_page), ("coverage", "span", "end"), END - FIVE_MINUTES)
    with pytest.raises(ContractViolationError, match="coverage"):
        decode(shortened, request)


def test_gapped_and_empty_pages_report_gap_free_false() -> None:
    request = request_with(3)
    gapped = decode(page_json(request, [candle_json(slot(0)), candle_json(slot(2))]), request)
    empty = decode(page_json(request, [], oldest=slot(0), newest=slot(1)), request)

    assert gapped.coverage.gap_free is False
    assert gapped.coverage.missing_slots == (END - START) // FIVE_MINUTES - 2
    assert empty.candles == ()
    assert empty.coverage.gap_free is False


def test_error_bodies_map_to_typed_errors() -> None:
    invalid = decode_error(
        400,
        error_body("invalid_parameter", "bad", {"parameter": "limit", "received": "5000", "maximum": 1000}),
        None,
    )
    assert type(invalid) is InvalidParameterError
    assert (invalid.status, invalid.code, invalid.message) == (400, "invalid_parameter", "bad")
    assert (invalid.parameter, invalid.received, invalid.maximum) == ("limit", "5000", 1000)

    odd = decode_error(
        400, error_body("invalid_parameter", details={"parameter": 1, "received": None, "maximum": True}), None
    )
    assert type(odd) is InvalidParameterError
    assert (odd.parameter, odd.received, odd.maximum) == (None, None, None)

    unknown = decode_error(404, error_body("unknown_series", details={"venue": "v", "symbol": "s"}), None)
    assert type(unknown) is UnknownSeriesError
    assert unknown.details == {"venue": "v", "symbol": "s"}

    not_ready = decode_error(503, error_body("not_ready", details={"reason": "database_unreadable"}), "5")
    assert type(not_ready) is NotReadyError
    assert (not_ready.reason, not_ready.retry_after_s) == ("database_unreadable", 5)

    mismatch = decode_error(503, error_body("not_ready", details={"reason": "schema_mismatch"}), None)
    assert type(mismatch) is NotReadyError
    assert mismatch.reason == "schema_mismatch"
    assert mismatch.retry_after_s is None

    for header in ("soon", "-1", "5.5", "", " 5", "5\n", "1234567"):
        bad = decode_error(503, error_body("not_ready", details={"reason": "database_missing"}), header)
        assert type(bad) is NotReadyError
        assert bad.retry_after_s is None, header

    for status, code in [(404, "not_found"), (405, "method_not_allowed"), (500, "internal_error")]:
        plain = decode_error(status, error_body(code, details={}), None)
        assert type(plain) is QuasarApiError
        assert (plain.status, plain.code) == (status, code)

    for status, code in [(400, "some_new_code"), (500, "unknown_series")]:
        plain = decode_error(status, error_body(code), None)
        assert type(plain) is QuasarApiError
        assert (plain.status, plain.code) == (status, code)


HTML = b"<html><body>Bad gateway</body></html>"


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (502, HTML),
        (504, HTML),
        (502, error_body("internal_error")),
        (429, error_body("internal_error")),
        (503, b"<html>maintenance</html>"),
        (404, HTML),
        (500, b"{}"),
        (400, encode({"error": {"code": 1, "message": "m", "details": {}}})),
        (400, encode({"error": {"code": "invalid_parameter", "message": "m"}})),
        (400, encode({"error": {"code": "invalid_parameter", "message": "m", "details": []}})),
        (400, encode({"error": []})),
        (302, b""),
        (204, b""),
        (201, error_body("internal_error")),
        (200, error_body("internal_error")),
    ],
)
def test_responses_not_attributable_to_the_api_are_unexpected(status: int, body: bytes) -> None:
    error = decode_error(status, body, "5")

    assert type(error) is UnexpectedResponseError
    assert error.status == status
    assert (error.excerpt == "") == (body == b"")
    assert error.excerpt == body.decode("utf-8")[:200]


def test_excerpt_is_cut_and_decoded_leniently() -> None:
    error = decode_error(502, b"\xff" + b"a" * 500, None)

    assert type(error) is UnexpectedResponseError
    assert len(error.excerpt) == 200
    assert error.excerpt.startswith("�")


def test_error_hierarchy() -> None:
    api = [InvalidParameterError, UnknownSeriesError, NotReadyError]
    others = [ContractViolationError, UnexpectedResponseError, QuasarUnavailableError]
    for cls in [QuasarApiError, *api, *others]:
        assert issubclass(cls, QuasarError)
    for cls in api:
        assert issubclass(cls, QuasarApiError)
        assert [other for other in api if other is not cls and issubclass(cls, other)] == []
    for cls in others:
        assert not issubclass(cls, QuasarApiError)
        assert [other for other in others if other is not cls and issubclass(cls, other)] == []
    assert not issubclass(QuasarApiError, tuple(api))

    source: dict[str, object] = {"parameter": "limit"}
    error = InvalidParameterError(400, "invalid_parameter", "m", source)
    source["parameter"] = "other"
    source["extra"] = 1
    assert error.details == {"parameter": "limit"}
    assert error.parameter == "limit"
