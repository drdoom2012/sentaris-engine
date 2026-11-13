"""Threaded `127.0.0.1` HTTP servers with scripted handlers and a request log (SE-6 Task 4)."""

import threading
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import final

import pytest

type ScriptedHandler = Callable[[BaseHTTPRequestHandler], None]


@final
class Server:
    """A running local server: its `base_url` and every request it received, as `(request line, headers)`."""

    def __init__(self, handler: ScriptedHandler) -> None:
        self.requests: list[tuple[str, dict[str, str]]] = []
        requests = self.requests

        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                requests.append((self.requestline, dict(self.headers.items())))
                handler(self)

            def log_message(self, format: str, *args: object) -> None:
                return None

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._server.daemon_threads = True
        self._server.block_on_close = False
        self._thread = threading.Thread(target=self._server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self._thread.start()
        self.base_url = f"http://127.0.0.1:{self._server.server_address[1]}"

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join()


@pytest.fixture
def release() -> Iterator[threading.Event]:
    """An event a blocked handler waits on; set at teardown, before the servers are shut down."""
    event = threading.Event()
    yield event
    event.set()


@pytest.fixture
def local_server(release: threading.Event) -> Iterator[Callable[[ScriptedHandler], Server]]:
    """A factory starting a server on `127.0.0.1:0` that runs `handler` for every `GET`; all are shut down at
    teardown."""
    servers: list[Server] = []

    def start(handler: ScriptedHandler) -> Server:
        server = Server(handler)
        servers.append(server)
        return server

    yield start
    release.set()
    for server in servers:
        server.close()


def respond(handler: BaseHTTPRequestHandler, status: int, body: bytes, content_type: str | None) -> None:
    """Answer the current request with `status`, an optional `Content-Type` and `body`."""
    handler.send_response(status)
    if content_type is not None:
        handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)
