"""Time validators and the instrument key (domain 6.1, 6.8; SE-3 spec 5.1, 5.2, N1, N2)."""

from decimal import Decimal
from enum import IntEnum

import pytest

from sentaris_engine.domain.errors import EvaluationTypeError
from sentaris_engine.domain.instrument import check_instrument_key
from sentaris_engine.domain.timing import MAX_TIME_MS, check_duration, check_instant
from tests.domain.evaluation_helpers import raises_exactly


class _IntSub(int):
    pass


class _StrSub(str):
    pass


class _Int(IntEnum):
    ONE = 1


INVALID_TIME: list[object] = [
    pytest.param(-1, id="minus-one"),
    pytest.param(2**53, id="2**53"),
    pytest.param(10**400, id="10**400"),
    pytest.param(-(10**400), id="-10**400"),
    pytest.param(True, id="True"),
    pytest.param(False, id="False"),
    pytest.param(1.0, id="float"),
    pytest.param(Decimal(1), id="Decimal"),
    pytest.param("1", id="str"),
    pytest.param(None, id="None"),
    pytest.param(_IntSub(1), id="int-subclass"),
    pytest.param(_Int.ONE, id="IntEnum"),
]


@pytest.mark.parametrize("value", INVALID_TIME)
def test_invalid_instant_is_refused(value: object) -> None:
    assert check_instant(1) == 1
    raises_exactly(EvaluationTypeError, lambda: check_instant(value))


@pytest.mark.parametrize("value", [*INVALID_TIME, pytest.param(0, id="zero")])
def test_invalid_duration_is_refused(value: object) -> None:
    assert check_duration(1) == 1
    raises_exactly(EvaluationTypeError, lambda: check_duration(value))


def test_valid_time_is_returned() -> None:
    assert MAX_TIME_MS == 2**53 - 1
    for value in (0, 1, 2**53 - 1):
        result = check_instant(value)
        assert type(result) is int and result == value
    for value in (1, 2**53 - 1):
        result = check_duration(value)
        assert type(result) is int and result == value


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("", id="empty"),
        pytest.param(None, id="None"),
        pytest.param(b"x", id="bytes"),
        pytest.param(_StrSub("x"), id="str-subclass"),
        pytest.param(1, id="int"),
    ],
)
def test_invalid_instrument_key_is_refused(value: object) -> None:
    assert check_instrument_key("x") == "x"
    raises_exactly(EvaluationTypeError, lambda: check_instrument_key(value))


@pytest.mark.parametrize("key", ["a b", "\ud800", "BTC/USDT:USDT"])
def test_instrument_key_is_opaque(key: str) -> None:
    assert check_instrument_key(key) is key
