"""The default urllib transport against real local servers (SE-6 spec 5.5, 5.6; AC-1, AC-6, AC-7)."""

import http.client
import socket
import threading
import urllib.error
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler
from typing import Final

import pytest

from sentaris_engine.infrastructure.quasar import (
    OpenInterestPage,
    QuasarClient,
    QuasarResponseError,
    QuasarTransportError,
)
from sentaris_engine.infrastructure.quasar.transport import urllib_transport
from tests.domain.evaluation_helpers import raises_exactly
from tests.infrastructure.local_server import Server, respond
from tests.infrastructure.quasar_bodies import REQUESTS, decode, load

type Start = Callable[[Callable[[BaseHTTPRequestHandler], None]], Server]

JSON: Final = "application/json"
OPEN_INTEREST: Final = REQUESTS["open_interest_example"]
OPEN_INTEREST_LINE: Final = (
    "GET /v1/open-interest?venue=binance-usdm&symbol=BTC/USDT:USDT&period=5m"
    f"&start={OPEN_INTEREST.start}&end={OPEN_INTEREST.end} HTTP/1.1"
)


def serving(status: int, body: bytes, content_type: str | None = JSON) -> Callable[[BaseHTTPRequestHandler], None]:
    def handler(request: BaseHTTPRequestHandler) -> None:
        respond(request, status, body, content_type)

    return handler


def read_open_interest(base_url: str, timeout_ms: int = 2000) -> tuple[OpenInterestPage, ...]:
    assert OPEN_INTEREST.series is not None
    return QuasarClient(base_url, timeout_ms).read_open_interest(
        OPEN_INTEREST.venue, OPEN_INTEREST.symbol, OPEN_INTEREST.series, OPEN_INTEREST.start, OPEN_INTEREST.end
    )


def cause_of(fn: Callable[[], object]) -> BaseException:
    """Run `fn`, require exactly `QuasarTransportError`, and return its chained cause."""
    with pytest.raises(BaseException) as info:
        fn()
    assert type(info.value) is QuasarTransportError
    assert info.value.__cause__ is not None
    return info.value.__cause__


def test_default_transport_reads_a_response(local_server: Start) -> None:
    # Behavior 8 (default part), AC-1: one `GET` in origin form with `Accept: application/json`.
    body = load("open_interest_example")
    server = local_server(serving(200, body, "application/json; charset=utf-8"))
    pages = read_open_interest(server.base_url)
    assert len(server.requests) == 1
    line, headers = server.requests[0]
    assert line == OPEN_INTEREST_LINE
    assert headers["Accept"] == "application/json"
    assert pages == (decode("open_interest_example"),)


def _status_of(base_url: str) -> tuple[int, str | None, str | None]:
    try:
        read_open_interest(base_url)
    except QuasarResponseError as exc:
        assert type(exc) is QuasarResponseError
        return exc.status, exc.code, exc.reason
    raise AssertionError("no QuasarResponseError was raised")


def test_non_200_is_a_status(local_server: Start) -> None:
    # AC-7: an `HTTPError` is read as a response; the client judges the status.
    not_found = local_server(serving(404, load("error_404_unknown_series")))
    assert _status_of(not_found.base_url) == (404, "unknown_series", None)
    broken = local_server(serving(500, b"<html>oops</html>", "text/html"))
    assert _status_of(broken.base_url) == (500, None, None)


def test_redirect_is_not_followed(local_server: Start) -> None:
    # AC-7, spec 5.6: a `3xx` is a status, and the target receives nothing.
    target = local_server(serving(200, load("open_interest_example")))

    def redirect(request: BaseHTTPRequestHandler) -> None:
        request.send_response(302)
        request.send_header("Location", f"{target.base_url}/v1/open-interest")
        request.send_header("Content-Length", "0")
        request.end_headers()

    origin = local_server(redirect)
    assert _status_of(origin.base_url) == (302, None, None)
    assert target.requests == []


def test_environment_proxy_is_ignored(local_server: Start, monkeypatch: pytest.MonkeyPatch) -> None:
    # AC-7, spec 5.6: nothing is taken from the environment.
    proxy = local_server(serving(500, b"proxy"))
    origin = local_server(serving(200, load("open_interest_example")))
    for name in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
        monkeypatch.setenv(name, proxy.base_url)
    for name in ("NO_PROXY", "no_proxy"):
        monkeypatch.delenv(name, raising=False)
    read_open_interest(origin.base_url)
    assert len(origin.requests) == 1
    assert proxy.requests == []


def test_requests_go_only_to_base_url_paths(local_server: Start) -> None:
    # AC-1, spec 5.6: three pages, each request line under the base URL's path prefix.
    names = ["candles_paged_1", "candles_paged_2", "candles_paged_3"]
    served = iter(names)

    def handler(request: BaseHTTPRequestHandler) -> None:
        respond(request, 200, load(next(served)), JSON)

    server = local_server(handler)
    first = REQUESTS[names[0]]
    assert first.series is not None
    pages = QuasarClient(f"{server.base_url}/q", 2000).read_candles(
        first.venue, first.symbol, first.series, first.start, first.end, first.limit
    )
    assert len(pages) == 3
    assert len(server.requests) == 3
    for line, headers in server.requests:
        assert line.startswith("GET /q/v1/candles?")
        assert line.endswith(" HTTP/1.1")
        assert headers["Accept"] == "application/json"


def _closed_port_url() -> str:
    # A socket bound without `listen()` does not refuse on this platform (macOS drops the connection attempt: a
    # `TimeoutError`), so the port is released and only the unlikelihood of another process taking it remains.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    return f"http://127.0.0.1:{port}"


def _truncated(status: int) -> Callable[[BaseHTTPRequestHandler], None]:
    def handler(request: BaseHTTPRequestHandler) -> None:
        request.send_response(status)
        request.send_header("Content-Type", JSON)
        request.send_header("Content-Length", "100")
        request.end_headers()
        request.wfile.write(b"0123456789")
        request.wfile.flush()
        request.close_connection = True

    return handler


def test_transport_failure_is_transport_error(local_server: Start, release: threading.Event) -> None:
    # Spec 5.5, 5.6, behavior 8, AC-6, Review Focus 6: the default transport's documented failures, with the
    # exact cause types CPython 3.12 produces.
    refused = cause_of(lambda: read_open_interest(_closed_port_url()))
    assert type(refused) is urllib.error.URLError
    assert type(refused.reason) is ConnectionRefusedError

    short_200 = local_server(_truncated(200))
    assert type(cause_of(lambda: read_open_interest(short_200.base_url))) is http.client.IncompleteRead

    short_500 = local_server(_truncated(500))
    assert type(cause_of(lambda: read_open_interest(short_500.base_url))) is http.client.IncompleteRead

    def say_nothing(request: BaseHTTPRequestHandler) -> None:
        release.wait()

    silent = local_server(say_nothing)
    assert type(cause_of(lambda: read_open_interest(silent.base_url, timeout_ms=200))) is TimeoutError


def test_default_transport_programming_error_propagates() -> None:
    # Spec 5.6: nothing but the listed failures is caught.
    raises_exactly(ValueError, lambda: urllib_transport("not a url", 1000))
    # Raised inside `opener.open` (name resolution rejects an empty label before any socket exists) by an
    # exception that is neither an `OSError` nor an `HTTPException`: it must not be translated.
    raises_exactly(UnicodeError, lambda: urllib_transport("http://a..b/", 1000))
