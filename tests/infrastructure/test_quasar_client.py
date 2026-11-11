import json
import time
import urllib.request
from collections.abc import Mapping
from decimal import Decimal
from types import MappingProxyType
from typing import Any, cast

import pytest

from sentaris_engine.infrastructure.quasar.client import (
    MAX_PAGE_LIMIT,
    MAX_WINDOW_SLOTS,
    TIMEFRAME_MS,
    QuasarClient,
)
from sentaris_engine.infrastructure.quasar.errors import (
    ContractViolationError,
    InvalidParameterError,
    NotReadyError,
    QuasarApiError,
    QuasarUnavailableError,
    UnexpectedResponseError,
    UnknownSeriesError,
)
from sentaris_engine.infrastructure.quasar.pages import PageRequest
from tests.support.quasar_fixtures import EXAMPLE_BODY, FIVE_MINUTES, candle_json, encode, error_body, page_json
from tests.support.quasar_stub import ScriptedResponse, StubQuasar, closed_port_url

VENUE = "binance-usdm"
SYMBOL = "BTC/USDT:USDT"
START = 1792643400000
END = START + 3 * FIVE_MINUTES
MIN_START = 946684800000
MAX_START = 4102444800000
MAX_END = MAX_START + FIVE_MINUTES
JSON = MappingProxyType({"Content-Type": "application/json"})


def three_candles() -> list[dict[str, object]]:
    return [
        candle_json(START, open="82855.4", high="82866.1", low="82768.1", close="82768.2", volume="369.221"),
        candle_json(START + FIVE_MINUTES, open="0.000012", high="1000", low="7", close="7.5"),
        candle_json(START + 2 * FIVE_MINUTES, turnover=None, volume="0.5"),
    ]


def fetch_three(client: QuasarClient, symbol: str = SYMBOL) -> Any:
    return client.fetch_page(VENUE, symbol, "5m", START, END)


def valid_page_body() -> bytes:
    request = PageRequest(VENUE, SYMBOL, "5m", FIVE_MINUTES, START, END, MAX_PAGE_LIMIT)
    return encode(page_json(request, [candle_json(START)]))


def scripted(status: int, body: bytes = b"", **headers: str) -> ScriptedResponse:
    return ScriptedResponse(status, body, MappingProxyType(headers))


def test_constants() -> None:
    assert MAX_PAGE_LIMIT == 1000
    assert MAX_WINDOW_SLOTS == 10_000
    assert dict(TIMEFRAME_MS) == {"5m": FIVE_MINUTES}


def test_stub_reproduces_the_contract_example(stub: StubQuasar) -> None:
    example = json.loads(EXAMPLE_BODY)
    candles = [candle_json(START + index * FIVE_MINUTES) for index in range(100)]
    candles[:3] = example["candles"]
    stub.add_series(VENUE, SYMBOL, FIVE_MINUTES, candles)
    query = f"venue=binance-usdm&symbol=BTC%2FUSDT%3AUSDT&timeframe=5m&start={START}&end=1792673400000&limit=3"
    with urllib.request.urlopen(f"{stub.base_url}/v1/candles?{query}", timeout=5) as response:
        body = response.read()
    assert json.loads(body) == example


def test_fetch_page_returns_the_stored_candles(stub: StubQuasar) -> None:
    stored = three_candles()
    stub.add_series(VENUE, SYMBOL, FIVE_MINUTES, stored)
    page = fetch_three(QuasarClient(stub.base_url))
    assert len(page.candles) == 3
    for candle, expected in zip(page.candles, stored, strict=True):
        assert candle.open_time_ms == expected["open_time_ms"]
        for name in ("open", "high", "low", "close", "volume"):
            assert getattr(candle, name).as_tuple() == Decimal(cast(str, expected[name])).as_tuple()
        if expected["turnover"] is None:
            assert candle.turnover is None
        else:
            assert candle.turnover is not None
            assert candle.turnover.as_tuple() == Decimal(cast(str, expected["turnover"])).as_tuple()
        assert candle.conflicted is False
    assert page.next_start is None
    assert page.start == START and page.end == END


def test_fetch_page_sends_only_documented_parameters(stub: StubQuasar) -> None:
    stub.add_series(VENUE, SYMBOL, FIVE_MINUTES, three_candles())
    fetch_three(QuasarClient(stub.base_url))
    assert len(stub.requests) == 1
    request = stub.requests[0]
    assert request.method == "GET"
    assert request.target.split("?")[0] == "/v1/candles"
    assert set(request.query) == {"venue", "symbol", "timeframe", "start", "end", "limit"}
    assert all(len(values) == 1 and values[0] != "" for values in request.query.values())
    assert request.query["limit"] == ["1000"]
    assert request.query["start"] == [str(START)]
    assert request.query["end"] == [str(END)]


@pytest.mark.parametrize(
    ("symbol", "raw"),
    [
        ("A/B:C", ()),
        ("A&B", ("&B",)),
        ("A+B", ("+",)),
        ("A#B", ("#",)),
        ("A%B", ()),
        ("A%2FB", ()),
        ("AéB", ("é",)),
        ("₿/USDT", ("₿",)),
    ],
)
def test_symbol_survives_query_encoding(stub: StubQuasar, symbol: str, raw: tuple[str, ...]) -> None:
    stub.add_series(VENUE, symbol, FIVE_MINUTES, three_candles())
    page = fetch_three(QuasarClient(stub.base_url), symbol)
    assert len(page.candles) == 3
    request = stub.requests[-1]
    assert request.query["symbol"] == [symbol]
    target_query = request.target.split("?", 1)[1]
    assert target_query.isascii()
    for fragment in raw:
        assert fragment not in target_query
    assert target_query.count("&") == 5  # only the separators between the six parameters
    assert "+" not in target_query and "#" not in target_query


def test_unknown_series_is_distinct_from_an_empty_window(stub: StubQuasar) -> None:
    stub.add_series(VENUE, SYMBOL, FIVE_MINUTES, three_candles())
    client = QuasarClient(stub.base_url)
    later = END + 10 * FIVE_MINUTES
    page = client.fetch_page(VENUE, SYMBOL, "5m", END, later)
    assert page.candles == ()
    assert page.coverage.gap_free is False
    with pytest.raises(UnknownSeriesError):
        client.fetch_page(VENUE, "NOPE/USDT:USDT", "5m", START, END)


def test_invalid_parameter_is_typed(stub: StubQuasar) -> None:
    details = {"parameter": "end", "received": "123", "maximum": 10000}
    stub.script(
        scripted(400, error_body("invalid_parameter", "too wide", details)),
        scripted(400, error_body("invalid_parameter", "too big", {"parameter": "limit", "received": "5000"})),
    )
    client = QuasarClient(stub.base_url)
    with pytest.raises(InvalidParameterError) as end_error:
        fetch_three(client)
    assert end_error.value.status == 400
    assert end_error.value.code == "invalid_parameter"
    assert end_error.value.parameter == "end"
    assert end_error.value.received == "123"
    assert end_error.value.maximum == 10000
    with pytest.raises(InvalidParameterError) as limit_error:
        fetch_three(client)
    assert limit_error.value.parameter == "limit"
    assert limit_error.value.received == "5000"
    assert limit_error.value.maximum is None


def test_not_ready_is_never_empty_data(stub: StubQuasar) -> None:
    unreadable = error_body("not_ready", "later", {"reason": "database_unreadable"})
    stub.script(
        scripted(503, unreadable, **{"Retry-After": "5"}),
        scripted(503, error_body("not_ready", "needs a deployment", {"reason": "schema_mismatch"})),
    )
    client = QuasarClient(stub.base_url)
    with pytest.raises(NotReadyError) as ready:
        fetch_three(client)
    assert ready.value.retry_after_s == 5
    assert ready.value.reason == "database_unreadable"
    with pytest.raises(NotReadyError) as mismatch:
        fetch_three(client)
    assert mismatch.value.retry_after_s is None
    assert mismatch.value.reason == "schema_mismatch"


def test_http_errors_are_not_reported_as_unavailable(stub: StubQuasar) -> None:
    stub.script(
        scripted(404, error_body("unknown_series", "no such series")),
        scripted(503, error_body("not_ready", "later")),
    )
    client = QuasarClient(stub.base_url)
    with pytest.raises(UnknownSeriesError):
        fetch_three(client)
    with pytest.raises(NotReadyError):
        fetch_three(client)


def test_other_documented_errors_are_api_errors(stub: StubQuasar) -> None:
    stub.script(scripted(500, error_body("internal_error", "boom")), scripted(404, error_body("not_found", "no route")))
    client = QuasarClient(stub.base_url)
    for status, code in ((500, "internal_error"), (404, "not_found")):
        with pytest.raises(QuasarApiError) as error:
            fetch_three(client)
        assert type(error.value) is QuasarApiError
        assert error.value.status == status
        assert error.value.code == code


@pytest.mark.parametrize("status", [502, 503, 404])
def test_proxy_pages_are_unexpected_responses(stub: StubQuasar, status: int) -> None:
    stub.script(scripted(status, b"<html><body>Bad Gateway</body></html>", **{"Content-Type": "text/html"}))
    with pytest.raises(UnexpectedResponseError) as error:
        fetch_three(QuasarClient(stub.base_url))
    assert error.value.status == status
    assert "Bad Gateway" in error.value.excerpt


@pytest.mark.parametrize("body", [b"", b"<html>"])
def test_garbage_200_is_unexpected(stub: StubQuasar, body: bytes) -> None:
    stub.script(scripted(200, body))
    with pytest.raises(UnexpectedResponseError) as error:
        fetch_three(QuasarClient(stub.base_url))
    assert error.value.status == 200


def test_json_200_that_is_not_a_page_is_a_contract_violation(stub: StubQuasar) -> None:
    stub.script(scripted(200, b"{}"))
    with pytest.raises(ContractViolationError) as error:
        fetch_three(QuasarClient(stub.base_url))
    assert error.value.status == 200


@pytest.mark.parametrize("status", [204, 201])
def test_other_2xx_is_unexpected(stub: StubQuasar, status: int) -> None:
    stub.script(scripted(status, valid_page_body() if status == 201 else b""))
    with pytest.raises(UnexpectedResponseError) as error:
        fetch_three(QuasarClient(stub.base_url))
    assert error.value.status == status


def test_redirect_is_not_followed(stub: StubQuasar) -> None:
    stub.add_series(VENUE, SYMBOL, FIVE_MINUTES, three_candles())
    location = f"{stub.base_url}/v1/candles?venue=x&symbol=y&timeframe=5m&start={START}&end={END}&limit=10"
    stub.script(scripted(302, b"", Location=location))
    with pytest.raises(UnexpectedResponseError) as error:
        fetch_three(QuasarClient(stub.base_url))
    assert error.value.status == 302
    assert len(stub.requests) == 1


def test_environment_proxy_is_honoured(stub: StubQuasar, monkeypatch: pytest.MonkeyPatch) -> None:
    stub.add_series(VENUE, SYMBOL, FIVE_MINUTES, three_candles())
    monkeypatch.delenv("NO_PROXY")
    monkeypatch.setenv("http_proxy", stub.base_url)
    page = fetch_three(QuasarClient("http://quasar.invalid"))
    assert len(page.candles) == 3
    assert stub.requests[0].target.startswith("http://quasar.invalid/v1/candles")


def test_connection_refused_is_unavailable() -> None:
    with pytest.raises(QuasarUnavailableError) as error:
        fetch_three(QuasarClient(closed_port_url()))
    assert error.value.__cause__ is not None


def test_stalled_read_is_unavailable(stub: StubQuasar) -> None:
    stub.script(ScriptedResponse(200, valid_page_body(), JSON, delay_s=1.0))
    started = time.monotonic()
    with pytest.raises(QuasarUnavailableError):
        fetch_three(QuasarClient(stub.base_url, timeout_s=0.2, deadline_s=5.0))
    assert time.monotonic() - started < 0.9


def test_slow_body_exceeds_the_deadline(stub: StubQuasar) -> None:
    stub.script(ScriptedResponse(200, valid_page_body(), JSON, drip=(100, 0.15)))
    started = time.monotonic()
    with pytest.raises(QuasarUnavailableError) as error:
        fetch_three(QuasarClient(stub.base_url, timeout_s=0.6, deadline_s=0.6))
    assert "deadline" in str(error.value)  # the per-operation timeout cannot be what ended it
    assert time.monotonic() - started < 3


def test_slow_error_body_exceeds_the_deadline(stub: StubQuasar) -> None:
    body = error_body("not_ready", "x" * 1500)
    stub.script(ScriptedResponse(503, body, JSON, drip=(100, 0.15)))
    started = time.monotonic()
    with pytest.raises(QuasarUnavailableError) as error:
        fetch_three(QuasarClient(stub.base_url, timeout_s=0.6, deadline_s=0.6))
    assert "deadline" in str(error.value)
    assert time.monotonic() - started < 3


@pytest.mark.parametrize("status", [200, 503])
def test_truncated_body_is_unavailable(stub: StubQuasar, status: int) -> None:
    stub.script(ScriptedResponse(status, b"0123456789", JSON, declared_length=1000))
    with pytest.raises(QuasarUnavailableError) as error:
        fetch_three(QuasarClient(stub.base_url))
    assert not isinstance(error.value, QuasarApiError)


def test_window_over_the_slot_cap_is_sent_and_left_to_quasar(stub: StubQuasar) -> None:
    details = {"parameter": "end", "received": "x", "maximum": 10000}
    stub.script(scripted(400, error_body("invalid_parameter", "too wide", details)))
    end = START + (MAX_WINDOW_SLOTS + 1) * FIVE_MINUTES
    with pytest.raises(InvalidParameterError):
        QuasarClient(stub.base_url).fetch_page(VENUE, SYMBOL, "5m", START, end)
    assert stub.requests[0].query["end"] == [str(end)]


def valid_args(**overrides: object) -> dict[str, object]:
    args: dict[str, object] = {
        "venue": VENUE,
        "symbol": SYMBOL,
        "timeframe": "5m",
        "start": START,
        "end": END,
        "limit": 10,
    }
    args.update(overrides)
    return args


@pytest.mark.parametrize(
    "overrides",
    [
        {"start": END},
        {"start": END + FIVE_MINUTES},
        {"start": True},
        {"end": True},
        {"start": float(START)},
        {"end": float(END)},
        {"start": MIN_START - FIVE_MINUTES, "end": MIN_START},
        {"start": MAX_START + FIVE_MINUTES, "end": MAX_START + 2 * FIVE_MINUTES},
        {"end": MAX_END + FIVE_MINUTES},
        {"start": START + 1},
        {"end": END + 1},
        {"limit": 0},
        {"limit": 1001},
        {"limit": True},
        {"limit": "5"},
        {"timeframe": "1m"},
        {"timeframe": ""},
        {"timeframe": 5},
        {"venue": ""},
        {"venue": None},
        {"venue": b"binance-usdm"},
        {"symbol": ""},
        {"symbol": None},
        {"symbol": 5},
    ],
    ids=lambda overrides: ",".join(f"{key}={value!r}" for key, value in overrides.items()),
)
def test_preconditions_are_value_errors(stub: StubQuasar, overrides: Mapping[str, object]) -> None:
    client = QuasarClient(stub.base_url)
    args = valid_args(**overrides)
    with pytest.raises(ValueError):
        client.fetch_page(**cast(Any, args))
    assert stub.requests == []


def test_the_documented_bounds_are_accepted(stub: StubQuasar) -> None:
    client = QuasarClient(stub.base_url)
    for start, end in ((MIN_START, MIN_START + FIVE_MINUTES), (MAX_START, MAX_END)):
        with pytest.raises(UnknownSeriesError):  # the stub has no series: the request was sent and answered
            client.fetch_page(VENUE, SYMBOL, "5m", start, end)
    assert [request.query["start"] for request in stub.requests] == [[str(MIN_START)], [str(MAX_START)]]


@pytest.mark.parametrize(
    "base_url",
    [
        "ftp://x",
        "localhost:8000",
        "http://",
        "http://h/path",
        "",
        5,
        "http://user:pw@127.0.0.1:1",
        "http://user@127.0.0.1:1",
        "http://h x:1",
        "http://" + "a" * 70 + ".com",
    ],
)
def test_base_url_is_validated(base_url: object) -> None:
    with pytest.raises(ValueError):
        QuasarClient(cast(Any, base_url))


@pytest.mark.parametrize("base_url", ["http://h", "http://h/", "https://h:8443/", "http://127.0.0.1:1"])
def test_base_url_is_accepted(base_url: str) -> None:
    QuasarClient(base_url)


@pytest.mark.parametrize(
    ("timeout_s", "deadline_s"),
    [
        (0, 30.0),
        (-1.0, 30.0),
        (True, 30.0),
        (10.0, 0),
        (10.0, -1.0),
        (10.0, True),
        (31.0, 30.0),
        (float("nan"), 30.0),
        (10.0, float("inf")),
        ("1", 30.0),
    ],
)
def test_time_bounds_are_validated(timeout_s: object, deadline_s: object) -> None:
    with pytest.raises(ValueError):
        QuasarClient("http://h", timeout_s=cast(Any, timeout_s), deadline_s=cast(Any, deadline_s))


def test_time_bounds_accept_ints_and_equal_values() -> None:
    QuasarClient("http://h", timeout_s=5, deadline_s=5)
