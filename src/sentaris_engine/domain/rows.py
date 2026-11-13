"""The rows of the three snapshot inputs (domain section 5; SE-3 spec 5.6).

Field checks only: no relation between fields is checked (OD-8), and nothing is filled or defaulted (DR-15).
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Final, final

from sentaris_engine.domain.errors import EvaluationTypeError
from sentaris_engine.domain.timing import check_instant

RATE_TYPES: Final = frozenset({"Regular", "Special"})


def _finite(value: object) -> Decimal:
    # Only context-free predicates, and `is_finite` first: NaN and sNaN must not reach a sign or comparison
    # (SE-3 spec 5.6).
    if type(value) is not Decimal or not value.is_finite():
        raise EvaluationTypeError("decimal field is not an exact finite Decimal (DR-11, SE-3 spec 5.6)")
    return value


def _non_negative(value: object) -> Decimal:
    """Exact finite `Decimal` without a negative sign; `Decimal("-0")` counts as negative."""
    decimal = _finite(value)
    if decimal.is_signed():
        raise EvaluationTypeError("decimal field is negative")
    return decimal


def _signed(value: object) -> Decimal:
    """Exact finite `Decimal` of either sign; `Decimal("-0")` is refused."""
    decimal = _finite(value)
    if decimal.is_zero() and decimal.is_signed():
        raise EvaluationTypeError("decimal field is a negative zero")
    return decimal


def _optional_non_negative(value: object) -> None:
    if value is not None:
        _non_negative(value)


def _check_conflicted(value: object) -> None:
    if type(value) is not bool:
        raise EvaluationTypeError("conflicted is not an exact bool (U2)")


@final
@dataclass(frozen=True, slots=True)
class Candle:
    """One candle of a series; the timeframe is the key of the series, not a field."""

    open_time: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    turnover: Decimal | None
    conflicted: bool

    def __post_init__(self) -> None:
        check_instant(self.open_time)
        _non_negative(self.open)
        _non_negative(self.high)
        _non_negative(self.low)
        _non_negative(self.close)
        _non_negative(self.volume)
        _optional_non_negative(self.turnover)
        _check_conflicted(self.conflicted)

    def __init_subclass__(cls, **kwargs: object) -> None:
        raise TypeError("Candle cannot be subclassed")


@final
@dataclass(frozen=True, slots=True)
class OpenInterest:
    """One open interest row; `time` is the end of the period."""

    time: int
    open_interest: Decimal
    open_interest_value: Decimal
    conflicted: bool

    def __post_init__(self) -> None:
        check_instant(self.time)
        _non_negative(self.open_interest)
        _non_negative(self.open_interest_value)
        _check_conflicted(self.conflicted)

    def __init_subclass__(cls, **kwargs: object) -> None:
        raise TypeError("OpenInterest cannot be subclassed")


@final
@dataclass(frozen=True, slots=True)
class FundingRate:
    """One funding settlement; a missing `mark_price` is the source's own null (OD-16)."""

    funding_time: int
    rate_type: str
    funding_rate: Decimal
    mark_price: Decimal | None
    conflicted: bool

    def __post_init__(self) -> None:
        check_instant(self.funding_time)
        if type(self.rate_type) is not str or self.rate_type not in RATE_TYPES:
            raise EvaluationTypeError("rate_type is not one of RATE_TYPES")
        _signed(self.funding_rate)
        _optional_non_negative(self.mark_price)
        _check_conflicted(self.conflicted)

    def __init_subclass__(cls, **kwargs: object) -> None:
        raise TypeError("FundingRate cannot be subclassed")
