"""`QuasarClient`: arguments, request URLs, paging and status mapping over an injected transport (SE-6 spec 5.1,
5.2, 5.5; AC-1, AC-2, AC-6, AC-8; behavior 1, 2, 7, 8, 9)."""

import dataclasses
from collections.abc import Callable
from typing import Any, Final
from urllib.parse import parse_qs, urlsplit

import pytest

from sentaris_engine.domain.errors import EvaluationTypeError
from sentaris_engine.domain.timing import MAX_TIME_MS
from sentaris_engine.infrastructure.quasar import (
    QuasarClient,
    QuasarProtocolError,
    QuasarResponseError,
    QuasarTransportError,
)
from tests.domain.evaluation_helpers import raises_exactly
from tests.infrastructure.quasar_bodies import DELETE, REQUESTS, Page, Request, decode, edited, load
from tests.infrastructure.quasar_fakes import FakeTransport, error, ok

BASE: Final = "http://q.test:8080"
TIMEOUT_MS: Final = 7000

PATHS: Final = {"candles": "/v1/candles", "open_interest": "/v1/open-interest", "funding": "/v1/funding-rates"}

# Sequences of bodies that make one whole read (every `next` of one is the `start` of the next).
SEQUENCES: Final = {
    "candles": ["candles_paged_1", "candles_paged_2", "candles_paged_3"],
    "open_interest": ["open_interest_paged_1", "open_interest_paged_2"],
    "funding": ["funding_paged_1", "funding_paged_2"],
}

# Bodies with `next: null`, one per endpoint, with and without `limit`.
SINGLE_PAGES: Final = [
    "candles_paged_3",
    "candles_empty",
    "open_interest_paged_2",
    "open_interest_example",
    "funding_paged_2",
    "funding_example",
]

# (fixture, status, code) of the contract section 2 error bodies.
ERROR_CASES: Final = [
    ("error_400_invalid_parameter", 400, "invalid_parameter"),
    ("error_404_unknown_series", 404, "unknown_series"),
    ("error_404_not_found", 404, "not_found"),
    ("error_405_method_not_allowed", 405, "method_not_allowed"),
    ("error_500_internal_error", 500, "internal_error"),
    ("error_503_not_ready", 503, "not_ready"),
]
FIRST_REQUESTS: Final = ["candles_empty", "open_interest_example", "funding_example"]


def client_for(transport: FakeTransport, base_url: str = BASE) -> QuasarClient:
    return QuasarClient(base_url, TIMEOUT_MS, transport)


def read(client: QuasarClient, request: Request) -> tuple[Page, ...]:
    """The whole read that `request` describes."""
    if request.endpoint == "funding":
        return client.read_funding_rates(request.venue, request.symbol, request.start, request.end, request.limit)
    if request.series is None:
        raise ValueError("a candle or open interest request needs a timeframe or period")
    if request.endpoint == "candles":
        return client.read_candles(
            request.venue, request.symbol, request.series, request.start, request.end, request.limit
        )
    return client.read_open_interest(
        request.venue, request.symbol, request.series, request.start, request.end, request.limit
    )


def raised(fn: Callable[[], object]) -> BaseException:
    with pytest.raises(BaseException) as info:
        fn()
    return info.value


def query(url: str) -> dict[str, str]:
    return {name: values[0] for name, values in parse_qs(urlsplit(url).query).items()}


def expected_url(base: str, request: Request, symbol: str = "BTC/USDT:USDT") -> str:
    """The URL of the first request, written out in the fixed parameter order (spec 5.2)."""
    parts = [f"venue={request.venue}", f"symbol={symbol}"]
    if request.series is not None:
        parts.append(f"{'timeframe' if request.endpoint == 'candles' else 'period'}={request.series}")
    parts += [f"start={request.start}", f"end={request.end}"]
    if request.limit is not None:
        parts.append(f"limit={request.limit}")
    return f"{base}{PATHS[request.endpoint]}?{'&'.join(parts)}"


def test_request_urls() -> None:
    # AC-1: the documented example, literally; then every endpoint with and without `limit`.
    transport = FakeTransport([ok(load("candles_paged_3"))])
    request = REQUESTS["candles_paged_3"]
    read(client_for(transport), request)
    url = (
        "http://q.test:8080/v1/candles?venue=binance-usdm&symbol=BTC/USDT:USDT&timeframe=5m"
        "&start=1792644900000&end=1792646400000&limit=2"
    )
    assert transport.calls == [(url, TIMEOUT_MS)]
    for name in SINGLE_PAGES:
        transport = FakeTransport([ok(load(name))])
        read(client_for(transport), REQUESTS[name])
        assert transport.calls == [(expected_url(BASE, REQUESTS[name]), TIMEOUT_MS)], name
        sent_limit = REQUESTS[name].limit
        assert query(transport.calls[0][0]).get("limit") == (None if sent_limit is None else str(sent_limit)), name


def test_identifiers_are_encoded_and_echo_compared_decoded() -> None:
    # Review Focus 2.
    symbol = "Ä B+%&#"
    request = dataclasses.replace(REQUESTS["candles_paged_3"], symbol=symbol)
    transport = FakeTransport([ok(edited("candles_paged_3", ("symbol",), symbol))])
    pages = read(client_for(transport), request)
    assert len(pages) == 1
    assert transport.calls[0][0] == expected_url(BASE, request, "%C3%84%20B%2B%25%26%23")


BASE_FORMS: Final = [
    ("http://127.0.0.1:8080/quasar/", "http://127.0.0.1:8080/quasar"),
    ("http://127.0.0.1:8080/quasar", "http://127.0.0.1:8080/quasar"),
    ("http://127.0.0.1:8080/quasar//", "http://127.0.0.1:8080/quasar"),
    ("https://h", "https://h"),
    ("https://h/", "https://h"),
    ("HTTP://H:80/", "http://H:80"),
    ("http://[::1]:9/", "http://[::1]:9"),
    ("http://[::1]", "http://[::1]"),
]


@pytest.mark.parametrize(("base_url", "prefix"), BASE_FORMS)
def test_base_url_forms(base_url: str, prefix: str) -> None:
    # Review Focus 3, R7.
    request = REQUESTS["candles_empty"]
    transport = FakeTransport([ok(load("candles_empty"))])
    read(client_for(transport, base_url), request)
    assert transport.calls == [(expected_url(prefix, request), TIMEOUT_MS)]


@pytest.mark.parametrize("name", ["open_interest_example", "funding_example"])
def test_single_page_read(name: str) -> None:
    # Behavior 1, AC-2: the contract examples 6.5.4 and 6.7.4 as whole reads.
    transport = FakeTransport([ok(load(name))])
    pages = read(client_for(transport), REQUESTS[name])
    assert pages == (decode(name),)
    assert len(transport.calls) == 1


@pytest.mark.parametrize("endpoint", list(SEQUENCES))
def test_paged_read(endpoint: str) -> None:
    # Behavior 2, AC-2.
    names = SEQUENCES[endpoint]
    first = REQUESTS[names[0]]
    transport = FakeTransport([ok(load(name)) for name in names])
    pages = read(client_for(transport), first)
    assert pages == tuple(decode(name) for name in names)
    sent = [query(url) for url, _ in transport.calls]
    assert [int(q["start"]) for q in sent] == [first.start, *(page.next for page in pages[:-1])]
    assert [int(q["start"]) for q in sent] == [REQUESTS[name].start for name in names]
    assert {q["end"] for q in sent} == {str(first.end)}
    assert {q.get("limit") for q in sent} == {None if first.limit is None else str(first.limit)}
    assert pages[-1].next is None


@pytest.mark.parametrize("endpoint", list(SEQUENCES))
def test_later_page_must_echo_cursor(endpoint: str) -> None:
    # Review Focus 5: the second response echoes the caller's start, not the first page's `next`.
    first = SEQUENCES[endpoint][0]
    transport = FakeTransport([ok(load(first)), ok(load(first))])
    raises_exactly(QuasarProtocolError, lambda: read(client_for(transport), REQUESTS[first]))
    assert len(transport.calls) == 2


@pytest.mark.parametrize("request_name", FIRST_REQUESTS)
@pytest.mark.parametrize(("fixture", "status", "code"), ERROR_CASES)
def test_error_status_is_response_error(request_name: str, fixture: str, status: int, code: str) -> None:
    # Behavior 7, AC-6.
    transport = FakeTransport([error(status, load(fixture))])
    exc = raised(lambda: read(client_for(transport), REQUESTS[request_name]))
    assert type(exc) is QuasarResponseError
    assert (exc.status, exc.code) == (status, code)
    assert exc.reason == ("database_missing" if status == 503 else None)
    assert len(transport.calls) == 1


@pytest.mark.parametrize("endpoint", list(SEQUENCES))
@pytest.mark.parametrize(("fixture", "status", "code"), ERROR_CASES)
def test_error_status_on_later_page_returns_nothing(endpoint: str, fixture: str, status: int, code: str) -> None:
    # Spec 8, 5.5: no partial tuple of pages.
    names = SEQUENCES[endpoint]
    transport = FakeTransport([ok(load(names[0])), error(status, load(fixture))])
    exc = raised(lambda: read(client_for(transport), REQUESTS[names[0]]))
    assert type(exc) is QuasarResponseError
    assert (exc.status, exc.code) == (status, code)
    assert len(transport.calls) == 2


@pytest.mark.parametrize("request_name", FIRST_REQUESTS)
def test_not_ready_is_an_error_not_empty_data(request_name: str) -> None:
    transport = FakeTransport([error(503, load("error_503_not_ready"))])
    outcome: list[object] = []
    exc = raised(lambda: outcome.append(read(client_for(transport), REQUESTS[request_name])))
    assert type(exc) is QuasarResponseError
    assert outcome == []


def test_redirect_status_is_response_error() -> None:
    transport = FakeTransport([error(302, b"", None)])
    exc = raised(lambda: read(client_for(transport), REQUESTS["candles_empty"]))
    assert type(exc) is QuasarResponseError
    assert (exc.status, exc.code, exc.reason) == (302, None, None)
    assert len(transport.calls) == 1


NOT_READY_BODIES: Final = [
    (load("error_503_not_ready"), "database_missing"),
    (edited("error_503_not_ready", ("error", "details", "reason"), DELETE), None),
    (edited("error_503_not_ready", ("error", "details"), DELETE), None),
]


@pytest.mark.parametrize(("body", "reason"), NOT_READY_BODIES)
def test_not_ready_reason(body: bytes, reason: str | None) -> None:
    transport = FakeTransport([error(503, body)])
    exc = raised(lambda: read(client_for(transport), REQUESTS["candles_empty"]))
    assert type(exc) is QuasarResponseError
    assert (exc.status, exc.code, exc.reason) == (503, "not_ready", reason)


def test_protocol_error_on_later_page_returns_nothing() -> None:
    second = edited("candles_paged_2", ("candles", 0, "open"), "82744.50")
    transport = FakeTransport([ok(load("candles_paged_1")), ok(second)])
    raises_exactly(QuasarProtocolError, lambda: read(client_for(transport), REQUESTS["candles_paged_1"]))
    assert len(transport.calls) == 2


def test_injected_transport_errors_propagate() -> None:
    # Behavior 8.
    failure = QuasarTransportError("refused")
    exc = raised(lambda: read(client_for(FakeTransport([failure])), REQUESTS["candles_empty"]))
    assert exc is failure


BROKEN_RESULTS: Final[list[object]] = [None, (200, "application/json", b"{}"), "x"]


@pytest.mark.parametrize("broken", BROKEN_RESULTS)
def test_transport_result_must_be_an_http_response(broken: object) -> None:
    # R8: a broken transport is a programming error.
    client = QuasarClient(BASE, TIMEOUT_MS, lambda url, timeout_ms: _any(broken))
    raises_exactly(TypeError, lambda: read(client, REQUESTS["candles_empty"]))


def test_injected_transport_programming_error_propagates() -> None:
    # Spec 8: not translated into a `QuasarClientError`.
    bug = RuntimeError("bug")
    exc = raised(lambda: read(client_for(FakeTransport([bug])), REQUESTS["candles_empty"]))
    assert exc is bug


class _StrSub(str):
    pass


class _IntSub(int):
    pass


def _any(value: object) -> Any:
    return value


GOOD_BASE: Final = "http://h"

CLIENT_CASES: Final[list[tuple[object, object, object, type[BaseException]]]] = [
    # (base_url, timeout_ms, transport, exception class); `...` stands for the injected fake.
    (1, TIMEOUT_MS, ..., TypeError),
    (None, TIMEOUT_MS, ..., TypeError),
    (b"http://h", TIMEOUT_MS, ..., TypeError),
    (_StrSub("http://h"), TIMEOUT_MS, ..., TypeError),
    ("", TIMEOUT_MS, ..., ValueError),
    ("h", TIMEOUT_MS, ..., ValueError),
    ("/v1", TIMEOUT_MS, ..., ValueError),
    ("http://h /x", TIMEOUT_MS, ..., ValueError),
    ("http://h\x00", TIMEOUT_MS, ..., ValueError),
    ("http://h\n", TIMEOUT_MS, ..., ValueError),
    ("http://h/é", TIMEOUT_MS, ..., ValueError),
    ("ftp://h", TIMEOUT_MS, ..., ValueError),
    ("http://", TIMEOUT_MS, ..., ValueError),
    ("http://:8080", TIMEOUT_MS, ..., ValueError),
    ("http://h:99999", TIMEOUT_MS, ..., ValueError),
    ("http://h:abc", TIMEOUT_MS, ..., ValueError),
    ("http://u:p@h", TIMEOUT_MS, ..., ValueError),
    ("http://h/a;b", TIMEOUT_MS, ..., ValueError),
    ("http://h/?", TIMEOUT_MS, ..., ValueError),
    ("http://h/?a=1", TIMEOUT_MS, ..., ValueError),
    ("http://h/#", TIMEOUT_MS, ..., ValueError),
    (GOOD_BASE, 0, ..., EvaluationTypeError),
    (GOOD_BASE, -1, ..., EvaluationTypeError),
    (GOOD_BASE, True, ..., EvaluationTypeError),
    (GOOD_BASE, 1.0, ..., EvaluationTypeError),
    (GOOD_BASE, "1", ..., EvaluationTypeError),
    (GOOD_BASE, None, ..., EvaluationTypeError),
    (GOOD_BASE, _IntSub(1), ..., EvaluationTypeError),
    (GOOD_BASE, MAX_TIME_MS + 1, ..., EvaluationTypeError),
    (GOOD_BASE, TIMEOUT_MS, "not callable", TypeError),
    (GOOD_BASE, TIMEOUT_MS, 5, TypeError),
]


@pytest.mark.parametrize(("base_url", "timeout_ms", "transport", "exc_type"), CLIENT_CASES)
def test_malformed_client_arguments_are_refused(
    base_url: object, timeout_ms: object, transport: object, exc_type: type[BaseException]
) -> None:
    # AC-8: refused at construction, before any request.
    fake = FakeTransport([])
    injected = fake if transport is ... else transport
    raises_exactly(exc_type, lambda: QuasarClient(_any(base_url), _any(timeout_ms), _any(injected)))
    assert fake.calls == []


def test_port_zero_to_65535_is_accepted() -> None:
    for port in (0, 1, 65535):
        QuasarClient(f"http://h:{port}", TIMEOUT_MS, FakeTransport([]))


_VALID: Final[dict[str, object]] = {
    "venue": "binance-usdm",
    "symbol": "BTC/USDT:USDT",
    "series": "5m",
    "start": 1792643400000,
    "end": 1792673400000,
    "limit": 3,
}

IDENTIFIER_VALUES: Final[list[tuple[object, type[BaseException]]]] = [
    (1, TypeError),
    (None, TypeError),
    (b"x", TypeError),
    (_StrSub("x"), TypeError),
    ("", ValueError),
    ("\ud800", ValueError),
    ("a\udfffb", ValueError),
]
INSTANT_VALUES: Final[list[object]] = ["1", 1.0, True, None, -1, MAX_TIME_MS + 1, _IntSub(1)]
LIMIT_VALUES: Final[list[tuple[object, type[BaseException]]]] = [
    (0, ValueError),
    (-1, ValueError),
    (True, TypeError),
    (1.0, TypeError),
    ("5", TypeError),
    (_IntSub(5), TypeError),
]


def _read_cases() -> list[tuple[str, str, object, type[BaseException]]]:
    cases: list[tuple[str, str, object, type[BaseException]]] = []
    for endpoint in ("candles", "open_interest", "funding"):
        keys = ("venue", "symbol", "start", "end", "limit") + (() if endpoint == "funding" else ("series",))
        for key in keys:
            if key in ("venue", "symbol", "series"):
                cases += [(endpoint, key, value, exc) for value, exc in IDENTIFIER_VALUES]
            elif key == "limit":
                cases += [(endpoint, key, value, exc) for value, exc in LIMIT_VALUES]
            else:
                cases += [(endpoint, key, value, EvaluationTypeError) for value in INSTANT_VALUES]
    return cases


def _call(client: QuasarClient, endpoint: str, args: dict[str, object]) -> object:
    a = {key: _any(value) for key, value in args.items()}
    if endpoint == "candles":
        return client.read_candles(a["venue"], a["symbol"], a["series"], a["start"], a["end"], a["limit"])
    if endpoint == "open_interest":
        return client.read_open_interest(a["venue"], a["symbol"], a["series"], a["start"], a["end"], a["limit"])
    return client.read_funding_rates(a["venue"], a["symbol"], a["start"], a["end"], a["limit"])


@pytest.mark.parametrize(("endpoint", "key", "value", "exc_type"), _read_cases())
def test_malformed_read_arguments_are_refused(
    endpoint: str, key: str, value: object, exc_type: type[BaseException]
) -> None:
    # AC-8: refused before the first request.
    fake = FakeTransport([])
    args = {**_VALID, key: value}
    raises_exactly(exc_type, lambda: _call(client_for(fake), endpoint, args))
    assert fake.calls == []


@pytest.mark.parametrize("endpoint", list(SEQUENCES))
def test_valid_arguments_reach_the_transport(endpoint: str) -> None:
    # The cases above are valid arguments with one edit: with no edit the read reaches the transport.
    fake = FakeTransport([error(500, b"")])
    raises_exactly(QuasarResponseError, lambda: _call(client_for(fake), endpoint, dict(_VALID)))
    assert len(fake.calls) == 1


def test_limit_none_omits_the_parameter() -> None:
    fake = FakeTransport([error(500, b"")])
    raises_exactly(QuasarResponseError, lambda: _call(client_for(fake), "candles", {**_VALID, "limit": None}))
    assert "limit" not in query(fake.calls[0][0])


@pytest.mark.parametrize("endpoint", list(SEQUENCES))
def test_repeated_read_is_equal(endpoint: str) -> None:
    # Behavior 9.
    names = SEQUENCES[endpoint]
    request = REQUESTS[names[0]]
    first = read(client_for(FakeTransport([ok(load(name)) for name in names])), request)
    second = read(client_for(FakeTransport([ok(load(name)) for name in names])), request)
    assert first == second
    assert len(first) == len(names)


def test_calls_are_not_made_before_arguments_are_checked() -> None:
    # An invalid `limit` after valid identifiers must not cost a request on a transport that would answer.
    fake = FakeTransport([ok(load("candles_empty"))])
    raises_exactly(ValueError, lambda: client_for(fake).read_candles("v", "s", "5m", 0, 1, 0))
    assert fake.calls == []
