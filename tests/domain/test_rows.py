"""Candle, open interest and funding rows (domain section 5, DR-11; SE-3 spec 5.6, N6)."""

import dataclasses
from decimal import Decimal
from enum import IntEnum

import pytest

from sentaris_engine.domain.errors import EvaluationTypeError
from sentaris_engine.domain.rows import RATE_TYPES, FundingRate
from tests.domain.evaluation_helpers import raises_exactly
from tests.domain.row_builders import build_with, candle, funding, open_interest


class _IntSub(int):
    pass


class _DecimalSub(Decimal):
    pass


class _Int(IntEnum):
    ONE = 1


# Field kinds: instant, non-negative, nullable non-negative, signed, bool, rate type.
_FIELDS: list[tuple[str, str, str]] = [
    ("Candle", "open_time", "instant"),
    ("Candle", "open", "non_negative"),
    ("Candle", "high", "non_negative"),
    ("Candle", "low", "non_negative"),
    ("Candle", "close", "non_negative"),
    ("Candle", "volume", "non_negative"),
    ("Candle", "turnover", "nullable_non_negative"),
    ("Candle", "conflicted", "bool"),
    ("OpenInterest", "time", "instant"),
    ("OpenInterest", "open_interest", "non_negative"),
    ("OpenInterest", "open_interest_value", "non_negative"),
    ("OpenInterest", "conflicted", "bool"),
    ("FundingRate", "funding_time", "instant"),
    ("FundingRate", "rate_type", "rate_type"),
    ("FundingRate", "funding_rate", "signed"),
    ("FundingRate", "mark_price", "nullable_non_negative"),
    ("FundingRate", "conflicted", "bool"),
]

_VALID: dict[str, object] = {
    "instant": 1,
    "non_negative": Decimal("1.5"),
    "nullable_non_negative": Decimal(0),
    "signed": Decimal("-0.00005123"),
    "bool": True,
    "rate_type": "Special",
}

_INVALID_INSTANT: list[object] = [
    -1,
    2**53,
    10**400,
    -(10**400),
    True,
    False,
    1.0,
    Decimal(1),
    "1",
    None,
    _IntSub(1),
    _Int.ONE,
]

_NOT_A_DECIMAL: list[object] = [1.0, Decimal("Infinity"), Decimal("-Infinity"), "1", 1, _DecimalSub("1")]
_NEGATIVE: list[object] = [Decimal(-1), Decimal("-0")]

_INVALID: dict[str, list[object]] = {
    "instant": _INVALID_INSTANT,
    "non_negative": [*_NOT_A_DECIMAL, None, *_NEGATIVE],
    "nullable_non_negative": [*_NOT_A_DECIMAL, *_NEGATIVE],
    "signed": [*_NOT_A_DECIMAL, None, Decimal("-0")],
    "bool": [0, 1, None],
    "rate_type": ["regular", "", None],
}

_INVALID_CASES = [
    pytest.param(row, field, value, id=f"{row}-{field}-{index}-{type(value).__name__}")
    for row, field, kind in _FIELDS
    for index, value in enumerate(_INVALID[kind])
]


@pytest.mark.parametrize(("row", "field", "invalid"), _INVALID_CASES)
def test_invalid_row_field_is_refused(row: str, field: str, invalid: object) -> None:
    kind = next(k for r, f, k in _FIELDS if (r, f) == (row, field))
    build_with(row, field, _VALID[kind])
    raises_exactly(EvaluationTypeError, lambda: build_with(row, field, invalid))


def test_funding_rate_is_signed_but_never_negative_zero() -> None:
    assert funding(1, funding_rate=Decimal("-0.00005123")).funding_rate == Decimal("-0.00005123")
    assert funding(1, funding_rate=Decimal(0)).funding_rate == Decimal(0)
    raises_exactly(EvaluationTypeError, lambda: funding(1, funding_rate=Decimal("-0")))


def test_non_negative_fields_accept_zero() -> None:
    assert candle(0, open=Decimal(0), volume=Decimal(0), turnover=Decimal(0)).volume == Decimal(0)
    assert open_interest(0, open_interest=Decimal(0)).open_interest == Decimal(0)
    assert funding(0, mark_price=Decimal(0)).mark_price == Decimal(0)


_DECIMAL_FIELDS = [(row, field) for row, field, kind in _FIELDS if kind not in ("instant", "bool", "rate_type")]

_NAN_KINDS = [Decimal("NaN"), Decimal("-NaN"), Decimal("sNaN"), Decimal("-sNaN")]


@pytest.mark.parametrize(
    ("row", "field", "invalid"),
    [
        pytest.param(row, field, value, id=f"{row}-{field}-{value}")
        for row, field in _DECIMAL_FIELDS
        for value in _NAN_KINDS
    ],
)
def test_decimal_nan_kinds_are_refused(row: str, field: str, invalid: Decimal) -> None:
    # Review Focus 1: a NaN kind raises EvaluationTypeError, never InvalidOperation from a sign or comparison check.
    build_with(row, field, Decimal(1))
    raises_exactly(EvaluationTypeError, lambda: build_with(row, field, invalid))


def test_nullable_fields() -> None:
    assert candle(0, turnover=None).turnover is None
    assert funding(0, mark_price=None).mark_price is None


def test_rate_types() -> None:
    assert RATE_TYPES == frozenset({"Regular", "Special"})
    for rate_type in sorted(RATE_TYPES):
        assert funding(0, rate_type).rate_type == rate_type


def test_rows_compare_by_fields() -> None:
    assert candle(0) == candle(0)
    assert hash(candle(0)) == hash(candle(0))
    # Representational only (spec 5.6): Python equality of Decimal, so the exponent does not matter.
    assert candle(0, open=Decimal("1.0")) == candle(0, open=Decimal("1.00"))
    assert hash(candle(0, open=Decimal("1.0"))) == hash(candle(0, open=Decimal("1.00")))
    assert candle(0) != candle(0, conflicted=True)
    assert candle(0) != candle(1)
    assert open_interest(0) == open_interest(0)
    assert open_interest(0) != open_interest(0, conflicted=True)
    assert funding(0) == funding(0)
    assert funding(0) != funding(0, "Special")
    assert funding(0) != funding(0, conflicted=True)
    other_row: object = open_interest(0)
    assert candle(0) != other_row


def test_replace_revalidates() -> None:
    # Review Focus 2: dataclasses.replace goes through construction, so it cannot produce an invalid row.
    valid = candle(0)
    assert dataclasses.replace(valid, open=Decimal(2)).open == Decimal(2)
    raises_exactly(EvaluationTypeError, lambda: dataclasses.replace(valid, open=Decimal(-1)))
    raises_exactly(EvaluationTypeError, lambda: dataclasses.replace(open_interest(0), time=-1))
    raises_exactly(EvaluationTypeError, lambda: dataclasses.replace(funding(0), rate_type="regular"))


def test_funding_rate_can_be_built_directly() -> None:
    row = FundingRate(funding_time=5, rate_type="Regular", funding_rate=Decimal(0), mark_price=None, conflicted=False)
    assert row == funding(5, mark_price=None, funding_rate=Decimal(0))
