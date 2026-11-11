"""A local HTTP server that records requests and answers them; it is NOT a model of Quasar.

It validates no parameter and implements no window or error logic: tests assert what the client sent from the
recording and script every error. The only data logic is what a paging test needs to receive self-consistent pages.
It holds no client logic and does not import the client. Imports nothing from `tests.*` except the page builders.
"""

import socket
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import MappingProxyType, TracebackType
from typing import NamedTuple, Self
from urllib.parse import parse_qs, urlsplit

from sentaris_engine.infrastructure.quasar.pages import PageRequest
from tests.support.quasar_fixtures import encode, error_body, page_json

CANDLES_PATH = "/v1/candles"


@dataclass(frozen=True, slots=True)
class RecordedRequest:
    """One request as the stub received it: `target` is the raw request target, `query` its parsed query."""

    method: str
    target: str
    query: dict[str, list[str]]


class ScriptedResponse(NamedTuple):
    """A response a test scripts instead of the normal one.

    `delay_s` is slept first. `Content-Length` is `declared_length` when given (the connection is then closed after
    `body`, so the length is a lie) and `len(body)` otherwise. `drip = (chunk_size, interval_s)` sends `body` in chunks
    of `chunk_size` bytes with `interval_s` between them.
    """

    status: int
    body: bytes = b""
    headers: Mapping[str, str] = MappingProxyType({})
    delay_s: float = 0.0
    declared_length: int | None = None
    drip: tuple[int, float] | None = None


@dataclass(slots=True)
class _Series:
    timeframe_ms: int
    candles: list[dict[str, object]]


class StubQuasar:
    """A context manager serving on `127.0.0.1` with an ephemeral port."""

    def __init__(self) -> None:
        self.requests: list[RecordedRequest] = []
        self.on_request: Callable[[int], None] | None = None
        self._lock = threading.Lock()
        self._series: dict[tuple[str, str], _Series] = {}
        self._scripted: dict[int, ScriptedResponse] = {}
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler_class())
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self.base_url = f"http://127.0.0.1:{self._server.server_address[1]}"

    def __enter__(self) -> Self:
        self._thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join()

    def _serve(self) -> None:
        self._server.serve_forever(poll_interval=0.01)  # a short poll keeps `shutdown()` from waiting 0.5 s

    def add_series(self, venue: str, symbol: str, timeframe_ms: int, candles: list[dict[str, object]]) -> None:
        """Serve `GET /v1/candles` for this series. `candles` stays owned by the caller, who may mutate it."""
        with self._lock:
            self._series[(venue, symbol)] = _Series(timeframe_ms, candles)

    def script(self, *responses: ScriptedResponse, after: int = 0) -> None:
        """Answer the next `after` requests normally, then the following ones with `responses`, then normally again."""
        with self._lock:
            first = len(self.requests) + after
            for offset, response in enumerate(responses):
                self._scripted[first + offset] = response

    def _handler_class(self) -> type[BaseHTTPRequestHandler]:
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                parts = urlsplit(self.path)
                with stub._lock:
                    index = len(stub.requests)
                    stub.requests.append(
                        RecordedRequest("GET", self.path, parse_qs(parts.query, keep_blank_values=True))
                    )
                    scripted = stub._scripted.pop(index, None)
                    query = stub.requests[index].query
                callback = stub.on_request
                if callback is not None:
                    callback(index)
                response = scripted if scripted is not None else stub._normal_response(parts.path, query)
                try:
                    self._send(response)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # the client gave up (a deadline or a timeout test); nothing to report

            def _send(self, response: ScriptedResponse) -> None:
                if response.delay_s:
                    time.sleep(response.delay_s)
                self.send_response(response.status)
                for name, value in response.headers.items():
                    self.send_header(name, value)
                length = len(response.body) if response.declared_length is None else response.declared_length
                self.send_header("Content-Length", str(length))
                self.end_headers()
                if response.drip is None:
                    self.wfile.write(response.body)
                else:
                    size, interval_s = response.drip
                    for offset in range(0, len(response.body), size):
                        if offset:
                            time.sleep(interval_s)
                        self.wfile.write(response.body[offset : offset + size])
                        self.wfile.flush()
                self.wfile.flush()

            def log_message(self, format: str, *args: object) -> None:
                pass

        return Handler

    def _normal_response(self, path: str, query: dict[str, list[str]]) -> ScriptedResponse:
        json_type = MappingProxyType({"Content-Type": "application/json"})
        if path != CANDLES_PATH:
            return ScriptedResponse(404, error_body("not_found"), json_type)
        venue, symbol = query["venue"][0], query["symbol"][0]
        with self._lock:
            series = self._series.get((venue, symbol))
            stored = [] if series is None else sorted(series.candles, key=_open_time)
        if series is None:
            return ScriptedResponse(404, error_body("unknown_series", "no such series"), json_type)
        start, end, limit = int(query["start"][0]), int(query["end"][0]), int(query["limit"][0])
        in_window = [candle for candle in stored if start <= _open_time(candle) < end]
        page = in_window[:limit]
        next_start = _open_time(in_window[limit]) if len(in_window) > limit else None
        request = PageRequest(venue, symbol, query["timeframe"][0], series.timeframe_ms, start, end, limit)
        body = page_json(
            request,
            page,
            oldest=_open_time(stored[0]),
            newest=_open_time(stored[-1]),
            next_start=next_start,
        )
        return ScriptedResponse(200, encode(body), json_type)


def _open_time(candle: dict[str, object]) -> int:
    return int(str(candle["open_time_ms"]))


def closed_port_url() -> str:
    """A base URL whose port was bound and then closed, so a connection to it is refused."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    return f"http://127.0.0.1:{port}"
