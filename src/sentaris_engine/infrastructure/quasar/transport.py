"""The HTTP response value and the transport type of the Quasar client (SE-6 spec 5.1; R8)."""

import http.client
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from email.message import Message
from typing import IO, final

from sentaris_engine.infrastructure.quasar.errors import QuasarTransportError


@final
@dataclass(frozen=True, slots=True)
class HttpResponse:
    """What a transport returns for every HTTP response, `200` or not."""

    status: int
    content_type: str | None
    body: bytes

    def __post_init__(self) -> None:
        if type(self.status) is not int:
            raise TypeError("status is not an exact int (R8)")
        if self.content_type is not None and type(self.content_type) is not str:
            raise TypeError("content_type is not an exact str or None (R8)")
        if type(self.body) is not bytes:
            raise TypeError("body is not exact bytes (R8)")

    def __init_subclass__(cls, **kwargs: object) -> None:
        raise TypeError("HttpResponse cannot be subclassed")


type Transport = Callable[[str, int], HttpResponse]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuses every redirect, so a `3xx` surfaces as an `HTTPError` and then as a status (spec 5.6)."""

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: Message,
        newurl: str,
    ) -> None:
        return None


def urllib_transport(url: str, timeout_ms: int) -> HttpResponse:
    """The default transport (spec 5.6): `GET` only, no proxy, no redirect; every network and I/O failure it
    documents is a `QuasarTransportError` (spec 5.5, U4)."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    request = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        # The only `float` of the client (spec 5.6; DR-11): the socket layer requires seconds.
        with opener.open(request, timeout=timeout_ms / 1000) as response:
            return HttpResponse(response.status, response.headers.get("Content-Type"), response.read())
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read()
        except (OSError, http.client.HTTPException) as read_failure:
            raise QuasarTransportError("the body of an error response could not be read") from read_failure
        finally:
            exc.close()
        return HttpResponse(exc.code, exc.headers.get("Content-Type"), body)
    except (OSError, http.client.HTTPException) as exc:
        raise QuasarTransportError("the request produced no HTTP response") from exc
