"""Stateless evaluation (DR-23, DR-26, DR-22, section 6.7; SE-4 N2, N4 to N9, Review Focus 1 to 5)."""

import inspect
from abc import ABCMeta
from enum import Enum

import pytest

from sentaris_engine.domain.context import EvaluationContext
from sentaris_engine.domain.declaration import Declaration
from sentaris_engine.domain.errors import EvaluationTypeError
from sentaris_engine.domain.evaluation import NotAnOutcome, evaluate_stateless
from sentaris_engine.domain.parameters import Parameters
from sentaris_engine.domain.payload import FrozenMapping
from sentaris_engine.domain.result import EvaluationFailure, NoSignal, Result, Signals
from sentaris_engine.domain.signal import Signal
from sentaris_engine.domain.strategy import NO_STATE, StatelessStrategy, StateTransition, StrategyIdentity
from tests.domain.evaluation_helpers import raises_exactly
from tests.domain.row_builders import snapshot
from tests.domain.strategy_helpers import (
    EMPTY_DECLARATION,
    IDENTITY,
    ContextSignalStrategy,
    MinimalStateful,
    MinimalStateless,
    RaisingStrategy,
    ReturningStrategy,
    VaryingStrategy,
    check_deterministic,
    make_context,
)


def _signal(kind: str = "k") -> Signal:
    return Signal(kind, FrozenMapping({}))


class _Colour(Enum):
    RED = "red"


def _assert_evaluation_refused(strategy: object, context: object) -> None:
    raises_exactly(EvaluationTypeError, lambda: evaluate_stateless(strategy, context))  # type: ignore[arg-type]


def _assert_not_an_outcome_refused(returned_type: object) -> None:
    raises_exactly(EvaluationTypeError, lambda: NotAnOutcome(returned_type))  # type: ignore[arg-type]


def test_contract_signatures_take_only_the_transition_inputs_evaluation() -> None:
    parameters = list(inspect.signature(evaluate_stateless).parameters.values())
    assert [p.name for p in parameters] == ["strategy", "context"]
    for p in parameters:
        assert p.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
        assert p.default is inspect.Parameter.empty


@pytest.mark.parametrize(
    "value",
    [
        None,
        _signal(),
        (_signal(),),
        [],
        NoSignal,
        StateTransition(NoSignal(), NO_STATE),
        NO_STATE,
        ValueError("x"),
        True,
        NotAnOutcome(int),
    ],
    ids=[
        "None",
        "Signal",
        "tuple-of-Signal",
        "list",
        "NoSignal-class",
        "StateTransition",
        "NO_STATE",
        "exception",
        "True",
        "NotAnOutcome",
    ],
)
def test_non_outcome_result_is_reported_as_value(value: object) -> None:
    r = evaluate_stateless(ReturningStrategy(value), make_context())
    assert type(r) is NotAnOutcome
    assert r.returned_type is type(value)
    assert r is not value


class _ClaimsToBeType:
    @property  # type: ignore[misc]
    def __class__(self) -> type:
        return type


def test_not_an_outcome_is_validated() -> None:
    invalids: tuple[object, ...] = (None, "int", 1, _ClaimsToBeType())
    for invalid in invalids:
        _assert_not_an_outcome_refused(invalid)
    for cls in (int, MinimalStateless, _Colour):
        assert NotAnOutcome(cls).returned_type is cls


class _Direct(BaseException):
    pass


@pytest.mark.parametrize(
    "exc",
    [ValueError("v"), EvaluationTypeError("e"), KeyboardInterrupt(), SystemExit(3), _Direct()],
    ids=["ValueError", "EvaluationTypeError", "KeyboardInterrupt", "SystemExit", "direct-BaseException"],
)
def test_strategy_exception_propagates_unchanged(exc: BaseException) -> None:
    cause = RuntimeError("cause")
    ctx = RuntimeError("ctx")
    exc.__cause__ = cause
    exc.__context__ = ctx
    strategy = RaisingStrategy(exc)
    with pytest.raises(BaseException) as info:
        evaluate_stateless(strategy, make_context())
    assert info.value is exc
    assert info.value.__cause__ is cause
    assert info.value.__context__ is ctx
    assert len(strategy.calls) == 1


class _PlainWithEvaluate:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def evaluate(self, context: object) -> Result:
        self.calls.append(context)
        return NoSignal()


class _ClaimsToBeStateless(_PlainWithEvaluate):
    @property  # type: ignore[misc]
    def __class__(self) -> type:
        return StatelessStrategy


class _ClaimsToBeContext:
    @property  # type: ignore[misc]
    def __class__(self) -> type:
        return EvaluationContext


class _RecordingStateful(MinimalStateful):
    def __init__(self) -> None:
        self.calls: list[object] = []

    def evaluate(self, context: EvaluationContext, previous_state: object) -> StateTransition:
        self.calls.append(context)
        return super().evaluate(context, previous_state)


def _function(context: object) -> Result:
    return NoSignal()


def test_malformed_evaluation_arguments_are_refused() -> None:
    stateful = _RecordingStateful()
    plain = _PlainWithEvaluate()
    spoofed = _ClaimsToBeStateless()
    strategies: tuple[object, ...] = (stateful, MinimalStateless, plain, _function, None, spoofed)
    for strategy in strategies:
        _assert_evaluation_refused(strategy, make_context())
    returning = ReturningStrategy(NoSignal())
    contexts: tuple[object, ...] = (None, snapshot(), {}, _ClaimsToBeContext())
    for context in contexts:
        _assert_evaluation_refused(returning, context)
    for calls in (stateful.calls, plain.calls, spoofed.calls, returning.calls):
        assert calls == []


class _PositionalOnly(StatelessStrategy):
    identity = IDENTITY

    def __init__(self, outcome: Result) -> None:
        self.outcome = outcome

    def evaluate(self, ctx: EvaluationContext, /) -> Result:
        return self.outcome

    def declare(self, parameters: Parameters) -> Declaration:
        return EMPTY_DECLARATION


def test_evaluate_is_called_positionally() -> None:
    outcome = NoSignal()
    assert evaluate_stateless(_PositionalOnly(outcome), make_context()) is outcome


@pytest.mark.parametrize(
    "strategy",
    [ContextSignalStrategy(), ReturningStrategy(NoSignal()), ReturningStrategy(EvaluationFailure("f"))],
    ids=["Signals", "NoSignal", "EvaluationFailure"],
)
def test_repeated_stateless_evaluation_is_identical(strategy: StatelessStrategy) -> None:
    """Repeated evaluation gives equal results (DR-26) for these test strategies only; not proof for any other strategy."""
    c = make_context()
    check_deterministic(strategy, [c])
    check_deterministic(strategy, [make_context(), make_context()])


def test_determinism_check_detects_a_varying_strategy() -> None:
    """Validates the determinism check against this one varying test strategy only."""
    with pytest.raises(AssertionError):
        check_deterministic(VaryingStrategy(), [make_context()])


def test_outcome_is_returned_unchanged() -> None:
    signals = Signals((_signal("zz"), _signal("mm"), _signal("aa")))
    for outcome in (signals, NoSignal(), EvaluationFailure("f")):
        c = make_context()
        strategy = ReturningStrategy(outcome)
        r = evaluate_stateless(strategy, c)
        assert r is outcome
        assert strategy.calls == [c]
        assert strategy.calls[0] is c
    r = evaluate_stateless(ReturningStrategy(signals), make_context())
    assert type(r) is Signals
    assert r.signals is signals.signals
    assert [s.kind for s in r.signals] == ["zz", "mm", "aa"]


def test_evaluation_is_independent_of_other_strategies() -> None:
    c = make_context()
    a = ContextSignalStrategy()
    first = evaluate_stateless(a, c)
    results = []
    evaluate_stateless(ReturningStrategy(EvaluationFailure("f")), c)
    results.append(evaluate_stateless(a, c))
    with pytest.raises(ValueError):
        evaluate_stateless(RaisingStrategy(ValueError("b")), c)
    results.append(evaluate_stateless(a, c))
    evaluate_stateless(ReturningStrategy(None), c)
    results.append(evaluate_stateless(a, c))
    for result in results:
        assert result == first
    assert len(a.calls) == 4
    for call in a.calls:
        assert call is c


class _HostileMeta(type):
    def __eq__(cls, other: object) -> bool:
        return True

    def __hash__(cls) -> int:
        return hash(Signals)

    def __instancecheck__(cls, instance: object) -> bool:
        return True

    def __subclasscheck__(cls, subclass: type) -> bool:
        return True

    def __repr__(cls) -> str:
        raise AssertionError("repr of the returned class")


class _Hostile(metaclass=_HostileMeta):
    pass


def test_non_outcome_with_hostile_metaclass_is_reported() -> None:
    r = evaluate_stateless(ReturningStrategy(_Hostile()), make_context())
    assert type(r) is NotAnOutcome
    assert r.returned_type is _Hostile


class _Explosive:
    @property  # type: ignore[misc]
    def __class__(self) -> type:
        return Signals

    def __eq__(self, other: object) -> bool:
        raise AssertionError("eq of the returned value")

    def __hash__(self) -> int:
        raise AssertionError("hash of the returned value")

    def __bool__(self) -> bool:
        raise AssertionError("bool of the returned value")

    def __repr__(self) -> str:
        raise AssertionError("repr of the returned value")


def test_non_outcome_value_is_not_touched() -> None:
    r = evaluate_stateless(ReturningStrategy(_Explosive()), make_context())
    assert type(r) is NotAnOutcome
    assert r.returned_type is _Explosive


def test_non_outcome_of_any_metaclass_is_reported() -> None:
    r = evaluate_stateless(ReturningStrategy(_Colour.RED), make_context())
    assert type(r) is NotAnOutcome
    assert r.returned_type is _Colour
    r = evaluate_stateless(ReturningStrategy(MinimalStateless()), make_context())
    assert type(r) is NotAnOutcome
    assert r.returned_type is MinimalStateless


def test_virtual_subclass_is_refused() -> None:
    calls: list[str] = []

    class Registered:
        @property
        def identity(self) -> StrategyIdentity:
            calls.append("identity")
            return IDENTITY

        def evaluate(self, context: EvaluationContext) -> Result:
            calls.append("evaluate")
            return NoSignal()

    ABCMeta.register(StatelessStrategy, Registered)

    class MroMeta(type):
        @property
        def __mro__(cls) -> tuple[type, ...]:
            return (cls, StatelessStrategy, object)

    class ClaimsMro(metaclass=MroMeta):
        @property
        def identity(self) -> StrategyIdentity:
            calls.append("identity")
            return IDENTITY

        def evaluate(self, context: EvaluationContext) -> Result:
            calls.append("evaluate")
            return NoSignal()

    strategies: tuple[object, ...] = (Registered(), ClaimsMro())
    for strategy in strategies:
        _assert_evaluation_refused(strategy, make_context())
    assert calls == []


def test_indirect_subclass_is_accepted() -> None:
    class Sub(ReturningStrategy):
        pass

    outcome = NoSignal()
    assert evaluate_stateless(Sub(outcome), make_context()) is outcome


class _UnreadableIdentity(StatelessStrategy):
    def __init__(self, outcome: Result) -> None:
        self.outcome = outcome

    @property
    def identity(self) -> StrategyIdentity:
        raise AssertionError("identity was read")

    def evaluate(self, context: EvaluationContext) -> Result:
        return self.outcome

    def declare(self, parameters: Parameters) -> Declaration:
        return EMPTY_DECLARATION


def test_identity_is_not_read() -> None:
    outcome = NoSignal()
    assert evaluate_stateless(_UnreadableIdentity(outcome), make_context()) is outcome


def test_not_an_outcome_repr_runs_no_strategy_code() -> None:
    repr(NotAnOutcome(_Hostile))
