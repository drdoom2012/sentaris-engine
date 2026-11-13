"""Instants and durations: exact integer UTC milliseconds (domain section 6.1; SE-3 U4, U6)."""

from typing import Final

from sentaris_engine.domain.errors import EvaluationTypeError

MAX_TIME_MS: Final = 2**53 - 1

type Instant = int
type Duration = int


def check_instant(value: object) -> int:
    """Return `value` if it is an exact `int` in `0 … MAX_TIME_MS` (U4)."""
    if type(value) is not int or not 0 <= value <= MAX_TIME_MS:
        raise EvaluationTypeError("instant is not an exact int in 0 … MAX_TIME_MS (U4)")
    return value


def check_duration(value: object) -> int:
    """Return `value` if it is an exact `int` in `1 … MAX_TIME_MS` (U6)."""
    if type(value) is not int or not 1 <= value <= MAX_TIME_MS:
        raise EvaluationTypeError("duration is not an exact int in 1 … MAX_TIME_MS (U6)")
    return value
