"""Time values (OD-10): instants are UTC milliseconds since the epoch, durations are milliseconds, both exact `int`.

An instant is not required to be non-negative and is not checked for alignment to a timeframe; neither is decided.
"""

type EpochMs = int
type DurationMs = int


def require_instant(value: object, name: str) -> EpochMs:
    """`value` if it is an exact `int` (not a `bool`, not a subclass), else `ValueError` naming `name`."""
    if type(value) is not int:
        raise ValueError(f"{name} must be an int of UTC milliseconds, got {type(value).__name__}")
    return value


def require_duration(value: object, name: str) -> DurationMs:
    """`value` if it is an exact `int` greater than zero (not a `bool`), else `ValueError` naming `name`."""
    if type(value) is not int:
        raise ValueError(f"{name} must be an int of milliseconds, got {type(value).__name__}")
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero, got {value}")
    return value
