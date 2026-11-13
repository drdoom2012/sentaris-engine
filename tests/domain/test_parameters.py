"""Parameters: flat scalar mappings with canonical equality (domain 6.5; SE-3 spec 5.3, N3)."""

from decimal import Decimal
from enum import IntEnum

import pytest

from sentaris_engine.domain.errors import EvaluationTypeError
from sentaris_engine.domain.parameters import Parameters
from sentaris_engine.domain.payload import FrozenMapping
from tests.domain.evaluation_helpers import raises_exactly


class _DecimalSub(Decimal):
    pass


class _Int(IntEnum):
    ONE = 1


# Each case is (valid baseline, the same source with one element changed).
INVALID_CASES: list[object] = [
    # values
    pytest.param({"a": 1}, {"a": None}, id="value-None"),
    pytest.param({"a": 1}, {"a": [1]}, id="value-list"),
    pytest.param({"a": 1}, {"a": (1,)}, id="value-tuple"),
    pytest.param({"a": 1}, {"a": {}}, id="value-dict"),
    pytest.param({"a": 1}, {"a": FrozenMapping({})}, id="value-FrozenMapping"),
    pytest.param({"a": 1}, {"a": 1.0}, id="value-float"),
    pytest.param({"a": Decimal(1)}, {"a": Decimal("NaN")}, id="value-Decimal-NaN"),
    pytest.param({"a": 2**53 - 1}, {"a": 2**53}, id="value-2**53"),
    pytest.param({"a": Decimal(1)}, {"a": _DecimalSub("1")}, id="value-Decimal-subclass"),
    pytest.param({"a": 1}, {"a": _Int.ONE}, id="value-IntEnum"),
    # keys
    pytest.param({"a": 1}, {1: 1}, id="key-int"),
    pytest.param({"a": 1}, {"\ud800": 1}, id="key-surrogate"),
    # pairs
    pytest.param([("a", 1), ("b", 2)], [("a", 1), ("a", 2)], id="pairs-duplicate-key"),
    # sources
    pytest.param({"a": 1}, None, id="source-None"),
    pytest.param({"a": 1}, {1}, id="source-set"),
    pytest.param({"a": 1}, 5, id="source-scalar"),
    pytest.param({"a": 1}, FrozenMapping({"a": 1}), id="source-FrozenMapping"),
]


@pytest.mark.parametrize(("valid", "invalid"), INVALID_CASES)
def test_invalid_parameters_are_refused(valid: object, invalid: object) -> None:
    Parameters(valid)
    raises_exactly(EvaluationTypeError, lambda: Parameters(invalid))


def test_parameters_equality_is_canonical() -> None:
    assert Parameters({"a": True}) != Parameters({"a": 1})
    assert Parameters({"a": 1}) != {"a": 1}
    assert {"a": 1} != Parameters({"a": 1})
    assert Parameters({"a": 1}) != FrozenMapping({"a": 1})
    assert FrozenMapping({"a": 1}) != Parameters({"a": 1})
    assert Parameters({}) == Parameters([])
    assert Parameters({}) != {}
    p = Parameters({"b": 1, "a": 2})
    q = Parameters([("a", 2), ("b", 1)])
    assert p == q
    assert hash(p) == hash(q)
    assert list(p) == ["a", "b"]
    assert list(q) == ["a", "b"]


def test_parameters_hold_values() -> None:
    p = Parameters({"k": Decimal("1.0")})
    value = p["k"]
    assert type(value) is Decimal
    assert value.as_tuple() == Decimal("1.0").as_tuple()
    assert len(p) == 1
