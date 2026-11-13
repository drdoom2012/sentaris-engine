"""The strict JSON body layer: Content-Type, UTF-8, JSON without `float` (SE-6 spec 5.4 "Body", 5.5; R2, R3, R6)."""

import json
from dataclasses import dataclass
from typing import Final, NoReturn, final

from sentaris_engine.infrastructure.quasar.errors import QuasarProtocolError


@final
@dataclass(frozen=True, slots=True)
class JsonFraction:
    """A JSON number with a fraction or exponent, kept as its raw text; neither a number nor a string (DR-11)."""

    text: str

    def __post_init__(self) -> None:
        if type(self.text) is not str:
            raise TypeError("text is not an exact str")

    def __init_subclass__(cls, **kwargs: object) -> None:
        raise TypeError("JsonFraction cannot be subclassed")


class _JsonRefused(Exception):
    """The client's private refusal error, raised by its own hooks (spec 5.4 exception table)."""


def _parse_float(text: str) -> JsonFraction:
    return JsonFraction(text)  # DR-11: no float is built


def _parse_int(text: str) -> int:
    try:
        return int(text)
    except ValueError as exc:  # only Python's integer-string digit limit (spec 5.4)
        raise _JsonRefused("integer longer than the integer-string digit limit") from exc


def _parse_constant(text: str) -> NoReturn:
    raise _JsonRefused(f"{text} is not JSON")


def _object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _JsonRefused("repeated key in an object")
        result[key] = value
    return result


# The spec 5.4 exception table, shared by the 200 path and the 5.5 predicate (R2).
PARSE_FAILURES: Final[tuple[type[Exception], ...]] = (
    UnicodeDecodeError,
    json.JSONDecodeError,
    RecursionError,
    _JsonRefused,
)


def parse_json(body: bytes) -> object:
    """Decode strictly as UTF-8 and parse with the client's hooks; raises the PARSE_FAILURES untranslated."""
    text = body.decode("utf-8")
    # The hooks are read from the module globals at each call (R3).
    return json.loads(
        text,
        parse_float=_parse_float,
        parse_int=_parse_int,
        parse_constant=_parse_constant,
        object_pairs_hook=_object_pairs,
    )


def _is_json_content_type(content_type: str | None) -> bool:
    """R6."""
    if content_type is None:
        return False
    media_type, *parameters = content_type.split(";")
    if media_type.strip(" \t").lower() != "application/json":
        return False
    for parameter in parameters:
        name, separator, value = parameter.partition("=")
        if not separator or name.strip(" \t").lower() != "charset":
            continue
        value = value.strip(" \t")
        if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        if value.lower() != "utf-8":
            return False
    return True


def decode_ok_body(content_type: str | None, body: bytes) -> dict[str, object]:
    """The top-level object of a `200` body, or `QuasarProtocolError` (spec 5.4 "Body")."""
    if not _is_json_content_type(content_type):
        raise QuasarProtocolError("Content-Type is not application/json with charset utf-8")
    try:
        tree = parse_json(body)
    except PARSE_FAILURES as exc:
        raise QuasarProtocolError("body is not strict UTF-8 JSON") from exc
    if type(tree) is not dict:
        raise QuasarProtocolError("top level of the body is not an object")
    return tree


def error_fields(status: int, body: bytes) -> tuple[str | None, str | None]:
    """`(code, reason)` of a non-`200` body by the spec 5.5 predicate; never raises a parse failure."""
    try:
        tree = parse_json(body)
    except PARSE_FAILURES:
        return None, None
    if type(tree) is not dict:
        return None, None
    error = tree.get("error")
    if type(error) is not dict:
        return None, None
    code = error.get("code")
    if type(code) is not str or not code:
        return None, None
    reason: str | None = None
    if status == 503 and code == "not_ready":
        details = error.get("details")
        if type(details) is dict:
            candidate = details.get("reason")
            if type(candidate) is str:
                reason = candidate
    return code, reason
