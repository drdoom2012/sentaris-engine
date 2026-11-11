"""The ways reading from Quasar can fail, as exceptions deriving from `QuasarError`.

Four distinct kinds, none of which is ever empty data (contract section 2: `503` is "no data", never "empty data"):
`QuasarApiError` (Quasar's own documented error), `ContractViolationError` (a `200` that claims to be a page and is
not), `UnexpectedResponseError` (a response that cannot be attributed to the Quasar API, such as what a proxy or
gateway produces) and `QuasarUnavailableError` (no complete response). The classification is by the shape of the
response, not a proof of its origin. Which evaluation failure code each becomes is not decided here (OD-3).
"""

from __future__ import annotations

from collections.abc import Mapping


class QuasarError(Exception):
    """Base of every failure of the Quasar client."""


class QuasarUnavailableError(QuasarError):
    """No complete response: connection refused or reset, truncated body, timeout, deadline exceeded."""


class ContractViolationError(QuasarError):
    """A `200` whose body is a strict-JSON object that is not a valid page under contract sections 3 and 5."""

    def __init__(self, message: str, status: int) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class UnexpectedResponseError(QuasarError):
    """A response that cannot be attributed to the Quasar API; `excerpt` is the start of its body, for diagnosis."""

    def __init__(self, message: str, status: int, excerpt: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.excerpt = excerpt


class QuasarApiError(QuasarError):
    """Quasar's own documented error: status 400, 404, 405, 500 or 503 with a well-formed contract section 2 body."""

    def __init__(self, status: int, code: str, message: str, details: Mapping[str, object]) -> None:
        super().__init__(f"{status} {code}: {message}")
        self.status = status
        self.code = code
        self.message = message
        self.details: Mapping[str, object] = dict(details)


class InvalidParameterError(QuasarApiError):
    """`400 invalid_parameter`; `parameter`, `received` and `maximum` are read from `details` when of the right type."""

    def __init__(self, status: int, code: str, message: str, details: Mapping[str, object]) -> None:
        super().__init__(status, code, message, details)
        parameter = self.details.get("parameter")
        received = self.details.get("received")
        maximum = self.details.get("maximum")
        self.parameter: str | None = parameter if type(parameter) is str else None
        self.received: str | None = received if type(received) is str else None
        self.maximum: int | None = maximum if type(maximum) is int else None


class UnknownSeriesError(QuasarApiError):
    """`404 unknown_series`: no candle of this series has ever been stored."""


class NotReadyError(QuasarApiError):
    """`503 not_ready`: Quasar cannot read its database. `retry_after_s` is the `Retry-After` header when valid.

    This is "no data", never "empty data" (contract section 2). Nothing here retries.
    """

    def __init__(
        self, status: int, code: str, message: str, details: Mapping[str, object], retry_after_s: int | None
    ) -> None:
        super().__init__(status, code, message, details)
        reason = self.details.get("reason")
        self.reason: str | None = reason if type(reason) is str else None
        self.retry_after_s = retry_after_s
