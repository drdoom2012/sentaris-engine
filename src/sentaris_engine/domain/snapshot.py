"""The immutable snapshot of one primary instrument at one `as_of` (domain sections 3, 6.6; DR-05; SE-3 spec 5.7).

Checks shape, order (DR-10) and the necessary condition of U1 only. No gap or grid check (OD-8, OD-16), no
availability claim (DR-06, OD-6), and no instrument key (section 6.8).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from itertools import pairwise
from types import MappingProxyType
from typing import final

from sentaris_engine.domain.errors import EvaluationTypeError
from sentaris_engine.domain.rows import Candle, FundingRate, OpenInterest
from sentaris_engine.domain.timing import check_duration, check_instant


def _candles(source: object, as_of: int) -> dict[int, tuple[Candle, ...]]:
    checked: dict[int, tuple[Candle, ...]] = {}
    for timeframe, series in _mapping(source).items():
        candles: list[Candle] = []
        for row in series:
            if type(row) is not Candle:
                raise EvaluationTypeError("candle series holds an element that is not an exact Candle")
            candles.append(row)
        for earlier, later in pairwise(candles):
            if not earlier.open_time < later.open_time:
                raise EvaluationTypeError("candles are not strictly ascending by open_time (DR-10)")
        for row in candles:
            # Exact integers: no overflow, wrap or clamp at MAX_TIME_MS (SE-3 spec section 6).
            if row.open_time + timeframe > as_of:
                raise EvaluationTypeError("candle is not closed at as_of (U1)")
        checked[timeframe] = tuple(candles)
    return checked


def _open_interest(source: object, as_of: int) -> dict[int, tuple[OpenInterest, ...]]:
    checked: dict[int, tuple[OpenInterest, ...]] = {}
    for period, series in _mapping(source).items():
        rows: list[OpenInterest] = []
        for row in series:
            if type(row) is not OpenInterest:
                raise EvaluationTypeError("open interest series holds an element that is not an exact OpenInterest")
            rows.append(row)
        for earlier, later in pairwise(rows):
            if not earlier.time < later.time:
                raise EvaluationTypeError("open interest is not strictly ascending by time (DR-10)")
        for row in rows:
            if row.time > as_of:
                raise EvaluationTypeError("open interest is stamped after as_of (U1)")
        checked[period] = tuple(rows)
    return checked


def _mapping(source: object) -> dict[int, tuple[object, ...]]:
    """Exact `dict` of valid durations to exact tuples, in ascending key order (DR-10)."""
    if type(source) is not dict:
        raise EvaluationTypeError("series mapping is not an exact dict")
    entries: dict[int, tuple[object, ...]] = {}
    for key, series in source.items():
        check_duration(key)
        if type(series) is not tuple:
            raise EvaluationTypeError("series is not an exact tuple")
        entries[key] = series
    return {key: entries[key] for key in sorted(entries)}


def _funding(source: object, as_of: int) -> tuple[FundingRate, ...] | None:
    if source is None:
        return None
    if type(source) is not tuple:
        raise EvaluationTypeError("funding is not None or an exact tuple")
    rows: list[FundingRate] = []
    for row in source:
        if type(row) is not FundingRate:
            raise EvaluationTypeError("funding holds an element that is not an exact FundingRate")
        rows.append(row)
    for earlier, later in pairwise(rows):
        # rate_type is an exact str, so tuple order compares it by code point (SE-3 spec 5.7).
        if not (earlier.funding_time, earlier.rate_type) < (later.funding_time, later.rate_type):
            raise EvaluationTypeError("funding is not strictly ascending by (funding_time, rate_type) (DR-10)")
    for row in rows:
        if row.funding_time > as_of:
            raise EvaluationTypeError("funding is stamped after as_of (U1)")
    return tuple(rows)


@final
@dataclass(frozen=True, slots=True, eq=False)
class Snapshot:
    """Absent (no key, `funding = None`) and empty (`()`) are kept apart and judged by neither (OD-13, OD-8).

    Equality and hash are by identity. `dataclasses.replace` is refused, since the stored mappings are not `dict`.
    """

    as_of: int
    candles: Mapping[int, tuple[Candle, ...]]
    open_interest: Mapping[int, tuple[OpenInterest, ...]]
    funding: tuple[FundingRate, ...] | None

    def __post_init__(self) -> None:
        as_of = check_instant(self.as_of)
        candles = _candles(self.candles, as_of)
        open_interest = _open_interest(self.open_interest, as_of)
        funding = _funding(self.funding, as_of)
        object.__setattr__(self, "candles", MappingProxyType(candles))
        object.__setattr__(self, "open_interest", MappingProxyType(open_interest))
        object.__setattr__(self, "funding", funding)

    def __init_subclass__(cls, **kwargs: object) -> None:
        raise TypeError("Snapshot cannot be subclassed")
