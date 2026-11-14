"""Forming a declaration from a strategy (domain section 6.9, SE-7a spec 5.5; AC-4, AC-5, AC-8)."""

import dataclasses
from abc import ABCMeta
from collections.abc import Callable, Iterator, Mapping
from functools import partial

import pytest

from sentaris_engine.domain.declaration import Declaration, InputKind, InputNeed
from sentaris_engine.domain.declaring import NotADeclaration, declare_inputs
from sentaris_engine.domain.errors import EvaluationTypeError
from sentaris_engine.domain.evaluation import NotAnOutcome
from sentaris_engine.domain.parameters import Parameters
from sentaris_engine.domain.payload import FrozenMapping
from sentaris_engine.domain.result import EvaluationFailure, NoSignal, Signals
from sentaris_engine.domain.signal import Signal
from sentaris_engine.domain.strategy import (
    NO_STATE,
    StatefulStrategy,
    StatelessStrategy,
    StateTransition,
    StrategyIdentity,
)
from tests.domain.evaluation_helpers import raises_exactly
from tests.domain.strategy_helpers import MinimalStateful, MinimalStateless

_HOUR = 3_600_000
_DECLARATION = Declaration((InputNeed(InputKind.CANDLES, _HOUR, 100 * _HOUR),))


def _params() -> Parameters:
    return Parameters({"k": 7})


class _RecordingStateless(MinimalStateless):
    """Overrides only `declare`: records each call's `args` and `kwargs`, returns `value` as given."""

    def __init__(self, value: object) -> None:
        self.value = value
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def declare(self, *args: object, **kwargs: object) -> Declaration:
        self.calls.append((args, kwargs))
        return self.value  # type: ignore[return-value]


class _RecordingStateful(MinimalStateful):
    def __init__(self, value: object) -> None:
        self.value = value
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def declare(self, *args: object, **kwargs: object) -> Declaration:
        self.calls.append((args, kwargs))
        return self.value  # type: ignore[return-value]


def test_declare_inputs_passes_only_the_parameters() -> None:
    strategy = _RecordingStateless(_DECLARATION)
    params = _params()
    declare_inputs(strategy, params)
    [(args, kwargs)] = strategy.calls
    assert args == (params,)
    assert args[0] is params
    assert kwargs == {}


def test_declare_inputs_returns_a_declaration_as_the_very_object() -> None:
    result = declare_inputs(_RecordingStateless(_DECLARATION), _params())
    assert result is _DECLARATION


def test_declare_inputs_returns_an_evaluation_failure_as_the_very_object() -> None:
    failure = EvaluationFailure("bad_lookback")
    result = declare_inputs(_RecordingStateless(failure), _params())
    assert result is failure


def _explosive(claimed: type) -> object:
    class Explosive:
        @property  # type: ignore[misc]
        def __class__(self) -> type:
            return claimed

        def __eq__(self, other: object) -> bool:
            raise AssertionError("eq of the returned value")

        def __hash__(self) -> int:
            raise AssertionError("hash of the returned value")

        def __bool__(self) -> bool:
            raise AssertionError("bool of the returned value")

        def __repr__(self) -> str:
            raise AssertionError("repr of the returned value")

    return Explosive()


def _hostile_meta_instance() -> object:
    class HostileMeta(type):
        def __eq__(cls, other: object) -> bool:
            return True

        def __hash__(cls) -> int:
            return hash(Declaration)

        def __instancecheck__(cls, instance: object) -> bool:
            return True

        def __subclasscheck__(cls, subclass: type) -> bool:
            return True

        def __repr__(cls) -> str:
            raise AssertionError("repr of the returned class")

    class Hostile(metaclass=HostileMeta):
        pass

    return Hostile()


def _signal() -> Signal:
    return Signal("k", FrozenMapping({}))


_NEED = InputNeed(InputKind.CANDLES, _HOUR, 100 * _HOUR)


@pytest.mark.parametrize(
    "make_value",
    [
        pytest.param(lambda: None, id="None"),
        pytest.param(lambda: NoSignal(), id="NoSignal"),
        pytest.param(lambda: Signals((_signal(),)), id="Signals"),
        pytest.param(lambda: StateTransition(NoSignal(), NO_STATE), id="StateTransition"),
        pytest.param(lambda: (_NEED,), id="tuple-of-InputNeed"),
        pytest.param(lambda: [_NEED], id="list-of-InputNeed"),
        pytest.param(lambda: NotAnOutcome(int), id="NotAnOutcome"),
        pytest.param(lambda: NotADeclaration(int), id="NotADeclaration"),
        pytest.param(lambda: _explosive(Declaration), id="claims-Declaration"),
        pytest.param(lambda: _explosive(EvaluationFailure), id="claims-EvaluationFailure"),
        pytest.param(_hostile_meta_instance, id="hostile-metaclass"),
    ],
)
def test_declare_inputs_reports_a_non_declaration_by_type_only(make_value: Callable[[], object]) -> None:
    value = make_value()
    real_class = type(value)
    result = declare_inputs(_RecordingStateless(value), _params())
    assert type(result) is NotADeclaration
    assert result.returned_type is real_class
    assert [f.name for f in dataclasses.fields(result)] == ["returned_type"]


def test_declare_inputs_propagates_an_exception_unchanged() -> None:
    exc = ValueError("v")
    strategy = _RecordingStateless(None)

    def declare(*args: object, **kwargs: object) -> Declaration:
        raise exc

    strategy.declare = declare  # type: ignore[method-assign]
    with pytest.raises(ValueError) as info:
        declare_inputs(strategy, _params())
    assert info.value is exc


class _UnreadableIdentityStateless(MinimalStateless):
    @property
    def identity(self) -> StrategyIdentity:  # type: ignore[override]
        raise AssertionError("identity was read")

    def declare(self, parameters: Parameters) -> Declaration:
        return _DECLARATION


def test_declare_inputs_does_not_read_identity() -> None:
    assert declare_inputs(_UnreadableIdentityStateless(), _params()) is _DECLARATION


class _PlainWithDeclare:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def declare(self, parameters: object) -> Declaration:
        self.calls.append(parameters)
        return _DECLARATION


class _ClaimsStateless(_PlainWithDeclare):
    @property  # type: ignore[misc]
    def __class__(self) -> type:
        return StatelessStrategy


class _ClaimsStateful(_PlainWithDeclare):
    @property  # type: ignore[misc]
    def __class__(self) -> type:
        return StatefulStrategy


class _MappingSub(Mapping[str, int]):
    def __getitem__(self, key: str) -> int:
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return iter(())

    def __len__(self) -> int:
        return 0


def test_declare_inputs_refuses_malformed_inputs_without_calling_declare() -> None:
    plain = _PlainWithDeclare()
    claims_stateless = _ClaimsStateless()
    claims_stateful = _ClaimsStateful()
    calls: list[str] = []

    class Registered:
        def declare(self, parameters: object) -> Declaration:
            calls.append("registered")
            return _DECLARATION

    ABCMeta.register(StatelessStrategy, Registered)

    class MroMeta(type):
        @property
        def __mro__(cls) -> tuple[type, ...]:
            return (cls, StatelessStrategy, object)

    class ClaimsMro(metaclass=MroMeta):
        def declare(self, parameters: object) -> Declaration:
            calls.append("claims-mro")
            return _DECLARATION

    recording = _RecordingStateless(_DECLARATION)
    strategies: tuple[object, ...] = (
        object(),
        MinimalStateless,
        plain,
        claims_stateless,
        claims_stateful,
        Registered(),
        ClaimsMro(),
    )
    for strategy in strategies:
        raises_exactly(EvaluationTypeError, partial(declare_inputs, strategy, _params()))  # type: ignore[arg-type]
    bad_parameters: tuple[object, ...] = ({"k": 7}, _MappingSub())
    for bad in bad_parameters:
        raises_exactly(EvaluationTypeError, partial(declare_inputs, recording, bad))  # type: ignore[arg-type]
    assert plain.calls == []
    assert claims_stateless.calls == []
    assert claims_stateful.calls == []
    assert calls == []
    assert recording.calls == []


def test_declare_inputs_serves_both_contracts() -> None:
    failure = EvaluationFailure("bad_lookback")
    params = _params()
    for contract_class in (_RecordingStateless, _RecordingStateful):
        declaring = contract_class(_DECLARATION)
        assert declare_inputs(declaring, params) is _DECLARATION
        failing = contract_class(failure)
        assert declare_inputs(failing, params) is failure
        result = declare_inputs(contract_class(None), params)
        assert type(result) is NotADeclaration
        assert result.returned_type is type(None)
        for strategy in (declaring, failing):
            [(args, kwargs)] = strategy.calls
            assert len(args) == 1
            assert args[0] is params
            assert kwargs == {}


def test_new_types_are_final_and_immutable_declaring() -> None:
    def subclass_not_a_declaration() -> None:
        class Sub(NotADeclaration):  # type: ignore[misc]
            pass

    raises_exactly(TypeError, subclass_not_a_declaration)
    value = NotADeclaration(int)
    raises_exactly(dataclasses.FrozenInstanceError, lambda: setattr(value, "returned_type", str))
    assert not hasattr(value, "__dict__")
    raises_exactly(EvaluationTypeError, lambda: NotADeclaration(1))  # type: ignore[arg-type]
    raises_exactly(EvaluationTypeError, lambda: dataclasses.replace(value, returned_type=None))  # type: ignore[arg-type]
    assert NotADeclaration(int) != NotADeclaration(int)

    class ReprMeta(type):
        def __repr__(cls) -> str:
            raise AssertionError("repr of the returned class")

    class C(metaclass=ReprMeta):
        pass

    repr(NotADeclaration(C))
