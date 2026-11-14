"""Strategy identity, the two contracts, absent state and the stateful outcome (domain sections 6.4, 6.8; SE-4 N1 to N3, N10 to N12)."""

import copy
import dataclasses
import inspect

import pytest

from sentaris_engine.domain.declaration import Declaration
from sentaris_engine.domain.errors import EvaluationTypeError
from sentaris_engine.domain.evaluation import NotAnOutcome
from sentaris_engine.domain.parameters import Parameters
from sentaris_engine.domain.payload import FrozenMapping, PayloadError
from sentaris_engine.domain.result import EvaluationFailure, NoSignal, Signals
from sentaris_engine.domain.signal import Signal
from sentaris_engine.domain.strategy import (
    NO_STATE,
    NoState,
    StatefulStrategy,
    StatelessStrategy,
    StateTransition,
    StrategyIdentity,
)
from tests.domain.evaluation_helpers import UNEXPECTED_IDS, UNEXPECTED_VALUES, raises_exactly
from tests.domain.strategy_helpers import EMPTY_DECLARATION, IDENTITY, MinimalStateful, MinimalStateless


class _StrSub(str):
    pass


def _is_valid_str_one(value: object) -> bool:
    return type(value) is str and value == "1"


_INVALID_IDENTITY_VALUES: list[object] = [
    "",
    None,
    1,
    b"x",
    _StrSub("x"),
    *(value for value in UNEXPECTED_VALUES if not _is_valid_str_one(value)),
]
_INVALID_IDENTITY_IDS: list[str] = [
    "empty",
    "None",
    "one",
    "bytes",
    "str-subclass",
    *(name for value, name in zip(UNEXPECTED_VALUES, UNEXPECTED_IDS, strict=True) if not _is_valid_str_one(value)),
]


@pytest.mark.parametrize("field", ["id", "version"])
@pytest.mark.parametrize("invalid", _INVALID_IDENTITY_VALUES, ids=_INVALID_IDENTITY_IDS)
def test_invalid_strategy_identity_is_refused(field: str, invalid: object) -> None:
    kwargs: dict[str, object] = {"id": "x", "version": "x", field: invalid}
    raises_exactly(EvaluationTypeError, lambda: StrategyIdentity(**kwargs))  # type: ignore[arg-type]


def test_strategy_identity_accepts_any_non_empty_str() -> None:
    StrategyIdentity("a b", "\ud800")
    assert StrategyIdentity("a", "1") == StrategyIdentity("a", "1")
    assert hash(StrategyIdentity("a", "1")) == hash(StrategyIdentity("a", "1"))
    assert StrategyIdentity("a", "1") != StrategyIdentity("a", "2")
    assert StrategyIdentity("a", "1") != ("a", "1")  # type: ignore[comparison-overlap]
    raises_exactly(TypeError, lambda: StrategyIdentity("a", "1") < StrategyIdentity("b", "1"))  # type: ignore[operator]


def test_contract_signatures_take_only_the_transition_inputs_contracts() -> None:
    stateless = inspect.signature(StatelessStrategy.evaluate)
    stateful = inspect.signature(StatefulStrategy.evaluate)
    assert list(stateless.parameters) == ["self", "context"]
    assert list(stateful.parameters) == ["self", "context", "previous_state"]
    for signature in (stateless, stateful):
        for parameter in signature.parameters.values():
            assert parameter.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
            assert parameter.default is inspect.Parameter.empty
    expected = frozenset({"identity", "evaluate", "declare"})
    assert StatelessStrategy.__abstractmethods__ == expected
    assert StatefulStrategy.__abstractmethods__ == expected


def _define_stateless_then_stateful() -> None:
    class C(StatelessStrategy, StatefulStrategy):  # type: ignore[misc]
        pass


def _define_stateful_then_stateless() -> None:
    class C(StatefulStrategy, StatelessStrategy):  # type: ignore[misc]
        pass


def _define_minimal_then_stateful() -> None:
    class C(MinimalStateless, StatefulStrategy):  # type: ignore[misc]
        pass


def _define_both_as_contract() -> None:
    class C(StatelessStrategy, StatefulStrategy, contract=True):  # type: ignore[misc]
        pass


def _define_third_root() -> None:
    class D(metaclass=type(StatelessStrategy), contract=True):  # type: ignore[metaclass, call-arg]
        pass


def _define_subclass_as_contract() -> None:
    class D(StatelessStrategy, contract=True):
        pass


class _Plain:
    pass


def test_strategy_cannot_take_both_contracts() -> None:
    raises_exactly(TypeError, _define_stateless_then_stateful)
    raises_exactly(TypeError, _define_stateful_then_stateless)
    raises_exactly(TypeError, _define_minimal_then_stateful)
    raises_exactly(TypeError, _define_both_as_contract)
    raises_exactly(TypeError, _define_third_root)
    raises_exactly(TypeError, _define_subclass_as_contract)
    raises_exactly(TypeError, lambda: StatelessStrategy.register(_Plain))
    raises_exactly(TypeError, lambda: StatefulStrategy.register(_Plain))
    MinimalStateless()
    MinimalStateful()


def test_contract_requires_evaluate_and_identity() -> None:
    class StatelessOnlyEvaluate(StatelessStrategy):
        def evaluate(self, context: object) -> NoSignal:
            return NoSignal()

        def declare(self, parameters: Parameters) -> Declaration:
            return EMPTY_DECLARATION

    class StatelessOnlyIdentity(StatelessStrategy):
        identity = IDENTITY

        def declare(self, parameters: Parameters) -> Declaration:
            return EMPTY_DECLARATION

    class StatefulOnlyEvaluate(StatefulStrategy):
        def evaluate(self, context: object, previous_state: object) -> StateTransition:
            return StateTransition(NoSignal(), previous_state)

        def declare(self, parameters: Parameters) -> Declaration:
            return EMPTY_DECLARATION

    class StatefulOnlyIdentity(StatefulStrategy):
        identity = IDENTITY

        def declare(self, parameters: Parameters) -> Declaration:
            return EMPTY_DECLARATION

    raises_exactly(TypeError, lambda: StatelessOnlyEvaluate())  # type: ignore[abstract]
    raises_exactly(TypeError, lambda: StatelessOnlyIdentity())  # type: ignore[abstract]
    raises_exactly(TypeError, lambda: StatefulOnlyEvaluate())  # type: ignore[abstract]
    raises_exactly(TypeError, lambda: StatefulOnlyIdentity())  # type: ignore[abstract]

    class StatelessWithProperty(StatelessStrategy):
        @property
        def identity(self) -> StrategyIdentity:
            return IDENTITY

        def evaluate(self, context: object) -> NoSignal:
            return NoSignal()

        def declare(self, parameters: Parameters) -> Declaration:
            return EMPTY_DECLARATION

    StatelessWithProperty()

    class StatefulWithProperty(StatefulStrategy):
        @property
        def identity(self) -> StrategyIdentity:
            return IDENTITY

        def evaluate(self, context: object, previous_state: object) -> StateTransition:
            return StateTransition(NoSignal(), previous_state)

        def declare(self, parameters: Parameters) -> Declaration:
            return EMPTY_DECLARATION

    StatefulWithProperty()


def test_declare_signature_takes_only_the_parameters() -> None:
    for contract in (StatelessStrategy, StatefulStrategy):
        signature = inspect.signature(contract.declare)
        assert list(signature.parameters) == ["self", "parameters"]
        for parameter in signature.parameters.values():
            assert parameter.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
            assert parameter.default is inspect.Parameter.empty


def test_strategy_without_declare_cannot_be_instantiated() -> None:
    class StatelessOnlyEvaluateAndIdentity(StatelessStrategy):
        identity = IDENTITY

        def evaluate(self, context: object) -> NoSignal:
            return NoSignal()

    class StatefulOnlyEvaluateAndIdentity(StatefulStrategy):
        identity = IDENTITY

        def evaluate(self, context: object, previous_state: object) -> StateTransition:
            return StateTransition(NoSignal(), previous_state)

    raises_exactly(TypeError, lambda: StatelessOnlyEvaluateAndIdentity())  # type: ignore[abstract]
    raises_exactly(TypeError, lambda: StatefulOnlyEvaluateAndIdentity())  # type: ignore[abstract]


def test_no_state_marker() -> None:
    assert NO_STATE is not None
    for other in (None, False, 0, "", ()):
        assert NO_STATE != other  # type: ignore[comparison-overlap]
    hash(NO_STATE)
    assert {NO_STATE: 1}[NO_STATE] == 1
    assert NoState() is NO_STATE
    assert copy.copy(NO_STATE) is NO_STATE
    assert copy.deepcopy(NO_STATE) is NO_STATE
    assert copy.deepcopy([NO_STATE])[0] is NO_STATE

    def define_subclass() -> None:
        class Sub(NoState):  # type: ignore[misc]
            pass

    raises_exactly(TypeError, define_subclass)
    raises_exactly(PayloadError, lambda: FrozenMapping({"a": NO_STATE}))
    raises_exactly(EvaluationTypeError, lambda: Parameters({"a": NO_STATE}))


def _signal() -> Signal:
    return Signal("k", FrozenMapping({}))


@pytest.mark.parametrize(
    "invalid",
    [
        None,
        _signal(),
        (_signal(),),
        [],
        NoSignal,
        NO_STATE,
        StateTransition(NoSignal(), None),
        ValueError("x"),
        True,
        *UNEXPECTED_VALUES,
    ],
    ids=[
        "None",
        "Signal",
        "tuple-of-Signal",
        "list",
        "NoSignal-class",
        "NO_STATE",
        "StateTransition",
        "exception",
        "True",
        *UNEXPECTED_IDS,
    ],
)
def test_state_transition_refuses_a_non_outcome(invalid: object) -> None:
    raises_exactly(EvaluationTypeError, lambda: StateTransition(invalid, None))  # type: ignore[arg-type]


class _EqualsEverythingMeta(type):
    def __eq__(cls, other: object) -> bool:
        return True

    def __hash__(cls) -> int:
        return hash(Signals)


class _ClaimsToBeSignals(metaclass=_EqualsEverythingMeta):
    pass


def test_state_transition_refuses_a_class_whose_metaclass_equals_an_outcome() -> None:
    raises_exactly(EvaluationTypeError, lambda: StateTransition(_ClaimsToBeSignals(), None))  # type: ignore[arg-type]


def test_state_transition() -> None:
    d: dict[str, int] = {"a": 1}
    for state in (NO_STATE, None, d, object()):
        assert StateTransition(NoSignal(), state).next_state is state
    assert d == {"a": 1}
    for outcome in (Signals((_signal(),)), NoSignal(), EvaluationFailure("c")):
        assert StateTransition(outcome, None).result is outcome
    assert StateTransition(NoSignal(), None) != StateTransition(NoSignal(), None)


def test_new_types_are_final_and_frozen_strategy() -> None:
    def subclass_identity() -> None:
        class Sub(StrategyIdentity):  # type: ignore[misc]
            pass

    def subclass_transition() -> None:
        class Sub(StateTransition):  # type: ignore[misc]
            pass

    def subclass_no_state() -> None:
        class Sub(NoState):  # type: ignore[misc]
            pass

    raises_exactly(TypeError, subclass_identity)
    raises_exactly(TypeError, subclass_transition)
    raises_exactly(TypeError, subclass_no_state)

    identity = StrategyIdentity("a", "1")
    transition = StateTransition(NoSignal(), None)
    raises_exactly(dataclasses.FrozenInstanceError, lambda: setattr(identity, "id", "b"))
    raises_exactly(dataclasses.FrozenInstanceError, lambda: setattr(identity, "version", "2"))
    raises_exactly(dataclasses.FrozenInstanceError, lambda: setattr(transition, "result", NoSignal()))
    raises_exactly(dataclasses.FrozenInstanceError, lambda: setattr(transition, "next_state", 1))
    raises_exactly(AttributeError, lambda: setattr(NO_STATE, "x", 1))
    for instance in (identity, transition, NO_STATE):
        assert not hasattr(instance, "__dict__")
    raises_exactly(EvaluationTypeError, lambda: dataclasses.replace(identity, id=""))


def test_state_transition_refuses_not_an_outcome() -> None:
    raises_exactly(EvaluationTypeError, lambda: StateTransition(NotAnOutcome(int), NO_STATE))  # type: ignore[arg-type]


def test_new_types_are_final_and_frozen_evaluation() -> None:
    def subclass_not_an_outcome() -> None:
        class Sub(NotAnOutcome):  # type: ignore[misc]
            pass

    raises_exactly(TypeError, subclass_not_an_outcome)
    value = NotAnOutcome(int)
    raises_exactly(dataclasses.FrozenInstanceError, lambda: setattr(value, "returned_type", str))
    assert not hasattr(value, "__dict__")
    raises_exactly(EvaluationTypeError, lambda: dataclasses.replace(value, returned_type=None))  # type: ignore[arg-type]


class _UnprintableState:
    def __repr__(self) -> str:
        raise AssertionError("repr of the state")


def test_state_transition_repr_runs_no_state_code() -> None:
    repr(StateTransition(NoSignal(), _UnprintableState()))
