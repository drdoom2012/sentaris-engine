"""The injected transport of the client tests and the responses it returns (SE-6 spec 8)."""

from typing import Final, final

from sentaris_engine.infrastructure.quasar import HttpResponse

JSON_UTF8: Final = "application/json; charset=utf-8"


def ok(body: bytes) -> HttpResponse:
    """A `200` JSON response with `body`."""
    return HttpResponse(200, JSON_UTF8, body)


def error(status: int, body: bytes, content_type: str | None = JSON_UTF8) -> HttpResponse:
    """A response with a status other than `200`."""
    return HttpResponse(status, content_type, body)


@final
class FakeTransport:
    """A transport that records `(url, timeout_ms)` and returns or raises the next scripted item; a call beyond
    the script fails the test."""

    def __init__(self, responses: list[HttpResponse | BaseException]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, int]] = []

    def __call__(self, url: str, timeout_ms: int) -> HttpResponse:
        self.calls.append((url, timeout_ms))
        if len(self.calls) > len(self._responses):
            raise AssertionError(f"transport called {len(self.calls)} times for {len(self._responses)} responses")
        item = self._responses[len(self.calls) - 1]
        if isinstance(item, BaseException):
            raise item
        return item
