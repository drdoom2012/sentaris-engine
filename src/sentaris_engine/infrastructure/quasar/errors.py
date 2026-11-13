"""Errors of the Quasar REST client (SE-6 spec 5.5)."""


class QuasarClientError(Exception):
    """Base of every client error; not an `EvaluationTypeError` (spec 5.5)."""


class QuasarTransportError(QuasarClientError):
    """The request produced no HTTP response; raised by a transport, never by the client itself."""


class QuasarResponseError(QuasarClientError):
    """An HTTP status other than `200`; `code` and `reason` come from the spec 5.5 predicate."""

    status: int
    code: str | None
    reason: str | None

    def __init__(self, status: int, code: str | None, reason: str | None) -> None:
        super().__init__(status, code, reason)
        self.status = status
        self.code = code
        self.reason = reason


class QuasarProtocolError(QuasarClientError):
    """A `200` response that breaks a check of spec 5.4."""
