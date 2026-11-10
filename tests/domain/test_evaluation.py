import copy
import pickle
from dataclasses import FrozenInstanceError
from decimal import Decimal
from typing import Any, cast

import pytest

from sentaris_engine.domain.evaluation import (
    EvaluationContext,
    EvaluationFailure,
    NoSignal,
    Result,
    Signal,
    Signals,
    StatelessStrategy,
)
from sentaris_engine.domain.market import Snapshot
from sentaris_engine.domain.parameters import Parameters
from sentaris_engine.domain.payload import Payload


class StrKind(str):
    pass


def make_signal(kind: str = "k", **payload: Any) -> Signal:
    return Signal(kind, Payload.of(payload))


def make_context(**overrides: Any) -> EvaluationContext:
    fields: dict[str, Any] = {"snapshot": Snapshot(()), "parameters": Parameters.of(), "as_of": 0}
    fields.update(overrides)
    return EvaluationContext(**fields)


def test_three_outcomes_are_distinct_types() -> None:
    signals = Signals((make_signal(),))
    outcomes: tuple[Result, ...] = (signals, NoSignal(), EvaluationFailure("x"))
    assert len({type(outcome) for outcome in outcomes}) == 3
    assert cast(Any, NoSignal()) != EvaluationFailure("x")
    assert cast(Any, signals) != NoSignal()
    assert NoSignal() == NoSignal()
    assert EvaluationFailure("x") == EvaluationFailure("x")
    assert EvaluationFailure("x") != EvaluationFailure("y")


def test_signals_must_be_a_non_empty_tuple_of_signals() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        Signals(())
    with pytest.raises(ValueError, match="tuple"):
        Signals(cast(Any, [make_signal()]))
    with pytest.raises(ValueError, match="tuple"):
        Signals(cast(Any, None))
    with pytest.raises(ValueError, match="Signal"):
        Signals(cast(Any, (make_signal(), "x")))
    with pytest.raises(ValueError, match="Signal"):
        Signals(cast(Any, ({"kind": "k"},)))
    assert Signals((make_signal(),)).signals == (make_signal(),)


def test_signals_keep_the_strategys_order() -> None:
    first = make_signal("z")
    second = make_signal("a")
    third = make_signal("m")
    assert Signals((first, second, third)).signals == (first, second, third)
    assert Signals((first, first)).signals == (first, first)


@pytest.mark.parametrize("kind", ["", None, 1, True, b"k", StrKind("k")], ids=repr)
def test_signal_requires_a_non_empty_str_kind(kind: Any) -> None:
    with pytest.raises(ValueError, match="kind"):
        Signal(kind, Payload.of())


@pytest.mark.parametrize("payload", [{}, {"a": 1}, None, [("a", 1)], "{}"], ids=repr)
def test_signal_requires_exactly_a_payload(payload: Any) -> None:
    with pytest.raises(ValueError, match="payload"):
        Signal("k", payload)


def test_signal_accepts_an_empty_payload_and_keeps_both_fields() -> None:
    signal = Signal("k", Payload.of())
    assert signal.kind == "k"
    assert signal.payload == Payload.of()


@pytest.mark.parametrize("code", ["", None, 1, True, b"x", StrKind("x")], ids=repr)
def test_failure_requires_non_empty_string_code(code: Any) -> None:
    with pytest.raises(ValueError, match="code"):
        EvaluationFailure(code)
    assert EvaluationFailure("any text at all, no format imposed").code == "any text at all, no format imposed"


def test_no_signal_takes_no_fields() -> None:
    with pytest.raises(TypeError):
        cast(Any, NoSignal)(1)


def test_signal_equality_uses_the_canonical_payload() -> None:
    one = make_signal("k", a=Decimal("1.0"))
    same = make_signal("k", a=Decimal("1.0"))
    other_scale = make_signal("k", a=Decimal("1.00"))
    assert Decimal("1.0") == Decimal("1.00")
    assert one == same
    assert hash(one) == hash(same)
    assert one != other_scale
    assert make_signal("k", a=True) != make_signal("k", a=1)
    assert make_signal("k") != make_signal("j")
    assert Signals((one,)) != Signals((other_scale,))


def test_signals_order_matters_for_equality() -> None:
    first = make_signal("a")
    second = make_signal("b")
    assert Signals((first, second)) == Signals((first, second))
    assert Signals((first, second)) != Signals((second, first))
    assert Signals((first,)) != Signals((first, first))


def test_context_carries_its_three_inputs() -> None:
    snapshot = Snapshot(())
    parameters = Parameters.of({"n": 3})
    context = EvaluationContext(snapshot, parameters, -5)
    assert context.snapshot is snapshot
    assert context.parameters is parameters
    assert context.as_of == -5
    assert make_context(as_of=1) != make_context(as_of=2)
    assert make_context(parameters=Parameters.of({"n": 1})) != make_context(parameters=Parameters.of({"n": 2}))


@pytest.mark.parametrize("as_of", [True, False, 1.0, "0", None, Decimal(0)], ids=repr)
def test_context_requires_exact_types_and_int_as_of(as_of: Any) -> None:
    with pytest.raises(ValueError, match="as_of"):
        make_context(as_of=as_of)


@pytest.mark.parametrize("snapshot", [(), {"series": ()}, None, [Snapshot(())]], ids=repr)
def test_context_requires_exactly_a_snapshot(snapshot: Any) -> None:
    with pytest.raises(ValueError, match="snapshot"):
        make_context(snapshot=snapshot)


@pytest.mark.parametrize("parameters", [{}, {"n": 1}, None, Payload.of(), [("n", 1)]], ids=repr)
def test_context_requires_exactly_parameters(parameters: Any) -> None:
    with pytest.raises(ValueError, match="parameters"):
        make_context(parameters=parameters)


def test_result_objects_are_immutable() -> None:
    signal = make_signal("k", a=1)
    signals = Signals((signal,))
    failure = EvaluationFailure("x")
    context = make_context()
    with pytest.raises(FrozenInstanceError):
        cast(Any, signal).kind = "other"
    with pytest.raises(FrozenInstanceError):
        cast(Any, signal).payload = Payload.of()
    with pytest.raises(FrozenInstanceError):
        cast(Any, signals).signals = ()
    with pytest.raises(FrozenInstanceError):
        cast(Any, failure).code = "y"
    with pytest.raises(FrozenInstanceError):
        cast(Any, context).as_of = 1
    with pytest.raises(FrozenInstanceError):
        cast(Any, context).snapshot = Snapshot(())
    with pytest.raises(TypeError):
        cast(Any, signals.signals)[0] = signal
    for value in (signal, signals, NoSignal(), failure, context):
        assert not hasattr(value, "__dict__")
        with pytest.raises((AttributeError, TypeError)):  # CPython's frozen+slots __setattr__ raises TypeError
            cast(Any, value).extra = 1


def test_results_survive_deepcopy_and_pickle() -> None:
    signals = Signals(
        (
            Signal("k", Payload.of({"p": Decimal("1.50"), "n": None, "l": [1, {"x": "\u00e9"}]})),
            Signal("j", Payload.of()),
        )
    )
    outcomes: tuple[Result, ...] = (signals, NoSignal(), EvaluationFailure("x"))
    for outcome in outcomes:
        for clone in (copy.copy(outcome), copy.deepcopy(outcome), pickle.loads(pickle.dumps(outcome))):
            assert type(clone) is type(outcome)
            assert clone == outcome
            assert hash(clone) == hash(outcome)
    clone = pickle.loads(pickle.dumps(signals))
    assert type(clone.signals) is tuple
    assert type(clone.signals[0]) is Signal
    assert type(clone.signals[0].payload) is Payload
    assert clone.signals[0].payload.canonical() == signals.signals[0].payload.canonical()
    context = make_context(parameters=Parameters.of({"n": Decimal("2.0")}), as_of=7)
    assert pickle.loads(pickle.dumps(context)) == context
    assert copy.deepcopy(context) == context


class AttributeStrategy:
    id = "attribute"
    version = "1"

    def evaluate(self, context: EvaluationContext) -> Result:
        return NoSignal()


class PropertyStrategy:
    @property
    def id(self) -> str:
        return "property"

    @property
    def version(self) -> str:
        return "2"

    def evaluate(self, context: EvaluationContext) -> Result:
        return EvaluationFailure("always")


def test_strategy_contract_accepts_attributes_and_properties() -> None:
    strategies: tuple[StatelessStrategy, ...] = (AttributeStrategy(), PropertyStrategy())
    results = [strategy.evaluate(make_context()) for strategy in strategies]
    assert results == [NoSignal(), EvaluationFailure("always")]
    assert [(strategy.id, strategy.version) for strategy in strategies] == [("attribute", "1"), ("property", "2")]
