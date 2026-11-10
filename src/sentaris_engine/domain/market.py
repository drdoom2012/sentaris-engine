"""Market data as the engine sees it: candles, a series of one timeframe, and the snapshot of series (DR-11, DR-15).

Values are carried exactly as given. Nothing is corrected, defaulted, merged or interpreted: a candle's numbers are not
related to each other, `turnover` stays null when Quasar sent none, and `conflicted` is not read (OD-7 is open). The
snapshot holds no `as_of` (that is the evaluation context's) and no instrument identity (OD-4).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from itertools import pairwise

from sentaris_engine.domain.timing import DurationMs, EpochMs, require_duration, require_instant


def _require_decimal(value: object, name: str) -> None:
    if type(value) is not Decimal:
        raise ValueError(f"{name} must be a Decimal, got {type(value).__name__}")
    if not value.is_finite():
        raise ValueError(f"{name} must be finite, got {value}")


@dataclass(frozen=True, slots=True)
class Candle:
    """One candle as Quasar sends it. The five numbers are exact, finite `Decimal`; `turnover` may also be `None`."""

    open_time_ms: EpochMs
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    turnover: Decimal | None
    conflicted: bool

    def __post_init__(self) -> None:
        require_instant(self.open_time_ms, "open_time_ms")
        _require_decimal(self.open, "open")
        _require_decimal(self.high, "high")
        _require_decimal(self.low, "low")
        _require_decimal(self.close, "close")
        _require_decimal(self.volume, "volume")
        if self.turnover is not None:
            _require_decimal(self.turnover, "turnover")
        if type(self.conflicted) is not bool:
            raise ValueError(f"conflicted must be a bool, got {type(self.conflicted).__name__}")


@dataclass(frozen=True, slots=True)
class CandleSeries:
    """The candles of one timeframe, a `tuple` strictly ascending by `open_time_ms`. Build unsorted input with `of`."""

    timeframe_ms: DurationMs
    candles: tuple[Candle, ...]

    def __post_init__(self) -> None:
        require_duration(self.timeframe_ms, "timeframe_ms")
        if type(self.candles) is not tuple:
            raise ValueError(f"candles must be a tuple, got {type(self.candles).__name__}")
        for candle in self.candles:
            if type(candle) is not Candle:
                raise ValueError(f"candles must hold Candle objects, got {type(candle).__name__}")
        for earlier, later in pairwise(self.candles):
            if later.open_time_ms <= earlier.open_time_ms:
                raise ValueError(
                    f"candles must be strictly ascending by open_time_ms; {later.open_time_ms} follows "
                    f"{earlier.open_time_ms}"
                )

    @staticmethod
    def of(timeframe_ms: int, candles: Iterable[Candle]) -> CandleSeries:
        """Sort `candles` ascending by open time. Two candles with one open time are rejected, never merged."""
        require_duration(timeframe_ms, "timeframe_ms")
        ordered = tuple(sorted(candles, key=_open_time))
        for earlier, later in pairwise(ordered):
            if later.open_time_ms == earlier.open_time_ms:
                raise ValueError(f"duplicate candle open_time_ms {later.open_time_ms}")
        return CandleSeries(timeframe_ms, ordered)


def _open_time(candle: Candle) -> EpochMs:
    if type(candle) is not Candle:
        raise ValueError(f"candles must hold Candle objects, got {type(candle).__name__}")
    return candle.open_time_ms


@dataclass(frozen=True, slots=True)
class Snapshot:
    """The series known at one evaluation, a `tuple` strictly ascending by `timeframe_ms`. Build with `of`."""

    series: tuple[CandleSeries, ...]

    def __post_init__(self) -> None:
        if type(self.series) is not tuple:
            raise ValueError(f"series must be a tuple, got {type(self.series).__name__}")
        for item in self.series:
            if type(item) is not CandleSeries:
                raise ValueError(f"series must hold CandleSeries objects, got {type(item).__name__}")
        for earlier, later in pairwise(self.series):
            if later.timeframe_ms <= earlier.timeframe_ms:
                raise ValueError(
                    f"series must be strictly ascending by timeframe_ms; {later.timeframe_ms} follows "
                    f"{earlier.timeframe_ms}"
                )

    @staticmethod
    def of(series: Iterable[CandleSeries]) -> Snapshot:
        """Sort `series` ascending by timeframe. Two series with one timeframe are rejected, never merged."""
        ordered = tuple(sorted(series, key=_timeframe))
        for earlier, later in pairwise(ordered):
            if later.timeframe_ms == earlier.timeframe_ms:
                raise ValueError(f"duplicate series timeframe_ms {later.timeframe_ms}")
        return Snapshot(ordered)

    def series_for(self, timeframe_ms: int) -> CandleSeries | None:
        """The series of `timeframe_ms`, or `None` if the snapshot has none."""
        require_duration(timeframe_ms, "timeframe_ms")
        for item in self.series:
            if item.timeframe_ms == timeframe_ms:
                return item
        return None


def _timeframe(series: CandleSeries) -> DurationMs:
    if type(series) is not CandleSeries:
        raise ValueError(f"series must hold CandleSeries objects, got {type(series).__name__}")
    return series.timeframe_ms
