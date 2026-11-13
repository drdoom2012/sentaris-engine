"""Signal and the three outcomes (domain section 6.2, 6.3, DR-14; SE-3 spec 5.4, 5.5, N4, N5)."""

import dataclasses

import pytest

from sentaris_engine.domain.errors import EvaluationTypeError
from sentaris_engine.domain.parameters import Parameters
from sentaris_engine.domain.payload import FrozenMapping
from sentaris_engine.domain.result import EvaluationFailure, NoSignal, Signals
from sentaris_engine.domain.signal import Signal
from tests.domain.evaluation_helpers import raises_exactly


class _StrSub(str):
    pass


def _signal(kind: str = "k") -> Signal:
    return Signal(kind, FrozenMapping({}))


@pytest.mark.parametrize(
    "invalid",
    [
        pytest.param(lambda: Signals(()), id="empty-tuple"),
        pytest.param(lambda: Signals([_signal()]), id="list"),  # type: ignore[arg-type]
        pytest.param(lambda: Signals((None,)), id="None-element"),  # type: ignore[arg-type]
        pytest.param(lambda: Signals(({},)), id="dict-element"),  # type: ignore[arg-type]
        pytest.param(lambda: Signals(((_signal(),),)), id="tuple-element"),  # type: ignore[arg-type]
        pytest.param(lambda: Signals((NoSignal(),)), id="NoSignal-element"),  # type: ignore[arg-type]
    ],
)
def test_signals_outcome_requires_signals(invalid: object) -> None:
    assert Signals((_signal(),)).signals == (_signal(),)
    raises_exactly(EvaluationTypeError, invalid)  # type: ignore[arg-type]


def test_signals_keep_order_and_duplicates() -> None:
    s1, s2 = _signal("a"), _signal("b")
    assert Signals((s1, s2)).signals == (s1, s2)
    assert Signals((s1, s2)) != Signals((s2, s1))
    assert Signals((s1, s1)).signals == (s1, s1)


@pytest.mark.parametrize(
    "code",
    [
        pytest.param("", id="empty"),
        pytest.param(None, id="None"),
        pytest.param(1, id="int"),
        pytest.param("\ud800", id="surrogate"),
        pytest.param(_StrSub("x"), id="str-subclass"),
    ],
)
def test_failure_requires_code(code: object) -> None:
    assert EvaluationFailure("x").code == "x"
    raises_exactly(EvaluationTypeError, lambda: EvaluationFailure(code))  # type: ignore[arg-type]


def test_outcomes_are_distinct() -> None:
    assert NoSignal() == NoSignal()
    outcomes: list[object] = [Signals((_signal(),)), NoSignal(), EvaluationFailure("x")]
    nothing: object = None
    for i, a in enumerate(outcomes):
        for j, b in enumerate(outcomes):
            assert (a == b) is (i == j)
        assert a != nothing
        assert (a == nothing) is False


@pytest.mark.parametrize(
    ("kind", "payload"),
    [
        pytest.param("", FrozenMapping({}), id="kind-empty"),
        pytest.param(None, FrozenMapping({}), id="kind-None"),
        pytest.param(1, FrozenMapping({}), id="kind-int"),
        pytest.param("\ud800", FrozenMapping({}), id="kind-surrogate"),
        pytest.param("k", {}, id="payload-dict"),
        pytest.param("k", None, id="payload-None"),
        pytest.param("k", Parameters({}), id="payload-Parameters"),
    ],
)
def test_invalid_signal_is_refused(kind: object, payload: object) -> None:
    assert Signal("k", FrozenMapping({})).kind == "k"
    raises_exactly(EvaluationTypeError, lambda: Signal(kind, payload))  # type: ignore[arg-type]


def test_signal_equality_is_canonical() -> None:
    assert Signal("k", FrozenMapping({"a": True})) != Signal("k", FrozenMapping({"a": 1}))
    assert Signal("k", FrozenMapping({"a": 1})) == Signal("k", FrozenMapping({"a": 1}))
    assert Signal("k", FrozenMapping({"a": 1})) != Signal("j", FrozenMapping({"a": 1}))
    assert hash(Signal("k", FrozenMapping({"a": 1}))) == hash(Signal("k", FrozenMapping({"a": 1})))


def test_replace_revalidates() -> None:
    assert dataclasses.replace(EvaluationFailure("x"), code="y").code == "y"
    raises_exactly(EvaluationTypeError, lambda: dataclasses.replace(EvaluationFailure("x"), code=""))
