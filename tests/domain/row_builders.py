"""Builders of valid rows and snapshots for the SE-3 tests; every default is valid, an override changes one field."""

import dataclasses
from collections.abc import Callable
from decimal import Decimal

from sentaris_engine.domain.rows import Candle, FundingRate, OpenInterest
from sentaris_engine.domain.snapshot import Snapshot


def _with[Row: (Candle, OpenInterest, FundingRate)](row: Row, overrides: dict[str, object]) -> Row:
    # Overrides may be deliberately invalid, so they are not typed against the row's fields.
    return dataclasses.replace(row, **overrides)  # type: ignore[arg-type]


def candle(open_time: int, **overrides: object) -> Candle:
    valid = Candle(
        open_time=open_time,
        open=Decimal(1),
        high=Decimal(2),
        low=Decimal(1),
        close=Decimal("1.5"),
        volume=Decimal(10),
        turnover=Decimal(15),
        conflicted=False,
    )
    return _with(valid, overrides)


def open_interest(time: int, **overrides: object) -> OpenInterest:
    valid = OpenInterest(
        time=time,
        open_interest=Decimal(100),
        open_interest_value=Decimal(5000),
        conflicted=False,
    )
    return _with(valid, overrides)


def funding(funding_time: int, rate_type: str = "Regular", **overrides: object) -> FundingRate:
    valid = FundingRate(
        funding_time=funding_time,
        rate_type=rate_type,
        funding_rate=Decimal("0.0001"),
        mark_price=Decimal(50),
        conflicted=False,
    )
    return _with(valid, overrides)


# Row name -> (builder, name of its instant field). The instant is the builder's first argument.
ROW_BUILDERS: dict[str, tuple[Callable[..., object], str]] = {
    "Candle": (candle, "open_time"),
    "OpenInterest": (open_interest, "time"),
    "FundingRate": (funding, "funding_time"),
}


def build_with(row: str, field: str, value: object) -> object:
    """Build a valid row of kind `row`, with `field` set to `value` (valid or not)."""
    builder, instant_field = ROW_BUILDERS[row]
    if field == instant_field:
        return builder(value)
    return builder(1, **{field: value})


def _snapshot_from(overrides: dict[str, object]) -> Snapshot:
    # Built directly, since `dataclasses.replace` of a snapshot is refused (N11).
    fields: dict[str, object] = {"as_of": 10_000_000, "candles": {}, "open_interest": {}, "funding": None, **overrides}
    # Overrides may be deliberately invalid, so they are not typed against the snapshot's fields.
    return Snapshot(**fields)  # type: ignore[arg-type]


def snapshot(as_of: int = 10_000_000, **overrides: object) -> Snapshot:
    """Build `Snapshot(as_of, {}, {}, None)` with `overrides` applied."""
    return _snapshot_from({"as_of": as_of, **overrides})


def snapshot_with(field: str, value: object) -> Snapshot:
    """Build the default snapshot with `field` set to `value` (valid or not)."""
    return _snapshot_from({field: value})
