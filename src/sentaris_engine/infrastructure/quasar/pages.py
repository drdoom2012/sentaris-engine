"""The page types: what Quasar answered to one request (SE-6 spec 5.3; R4, R5)."""

from dataclasses import dataclass
from typing import final

from sentaris_engine.domain.rows import Candle, FundingRate, OpenInterest
from sentaris_engine.domain.timing import MAX_TIME_MS


def _check_instant(name: str, value: object) -> None:
    # The `check_instant` predicate (R5), with the plain construction errors of R4.
    if type(value) is not int:
        raise TypeError(f"{name} is not an exact int")
    if not 0 <= value <= MAX_TIME_MS:
        raise ValueError(f"{name} is not in 0 … MAX_TIME_MS")


def _check_next(value: object) -> None:
    if value is not None:
        _check_instant("next", value)


def _check_rows(value: object, row_type: type) -> None:
    if type(value) is not tuple:
        raise TypeError("rows is not an exact tuple")
    for row in value:
        if type(row) is not row_type:
            raise TypeError(f"a row is not an exact {row_type.__name__}")


def _check_series(value: object) -> None:
    if type(value) is not SeriesBounds:
        raise TypeError("series is not a SeriesBounds")


@final
@dataclass(frozen=True, slots=True)
class SeriesBounds:
    """The oldest and newest stored time of the series at the moment of one request."""

    oldest: int
    newest: int

    def __post_init__(self) -> None:
        _check_instant("oldest", self.oldest)
        _check_instant("newest", self.newest)
        if self.oldest > self.newest:
            raise ValueError("oldest is after newest")

    def __init_subclass__(cls, **kwargs: object) -> None:
        raise TypeError("SeriesBounds cannot be subclassed")


@final
@dataclass(frozen=True, slots=True)
class CandlePage:
    """One `GET /v1/candles` page; `start` and `end` are the echoed window."""

    start: int
    end: int
    series: SeriesBounds
    rows: tuple[Candle, ...]
    next: int | None

    def __post_init__(self) -> None:
        _check_instant("start", self.start)
        _check_instant("end", self.end)
        _check_series(self.series)
        _check_rows(self.rows, Candle)
        _check_next(self.next)

    def __init_subclass__(cls, **kwargs: object) -> None:
        raise TypeError("CandlePage cannot be subclassed")


@final
@dataclass(frozen=True, slots=True)
class OpenInterestPage:
    """One `GET /v1/open-interest` page; `start` and `end` are the echoed window."""

    start: int
    end: int
    series: SeriesBounds
    rows: tuple[OpenInterest, ...]
    next: int | None

    def __post_init__(self) -> None:
        _check_instant("start", self.start)
        _check_instant("end", self.end)
        _check_series(self.series)
        _check_rows(self.rows, OpenInterest)
        _check_next(self.next)

    def __init_subclass__(cls, **kwargs: object) -> None:
        raise TypeError("OpenInterestPage cannot be subclassed")


@final
@dataclass(frozen=True, slots=True)
class FundingRatePage:
    """One `GET /v1/funding-rates` page; `series` is `None` when Quasar reports both bounds `null` (contract 6.7.4)."""

    start: int
    end_inclusive: int
    series: SeriesBounds | None
    rows: tuple[FundingRate, ...]
    next: int | None

    def __post_init__(self) -> None:
        _check_instant("start", self.start)
        _check_instant("end_inclusive", self.end_inclusive)
        if self.series is not None:
            _check_series(self.series)
        _check_rows(self.rows, FundingRate)
        _check_next(self.next)

    def __init_subclass__(cls, **kwargs: object) -> None:
        raise TypeError("FundingRatePage cannot be subclassed")
