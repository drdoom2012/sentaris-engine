"""The SE-5 value types and type names: N9 (direct), N12 and N13 of the SE-5 specification."""

import dataclasses
from collections.abc import Callable
from functools import partial

import pytest

from sentaris_engine.application.execution import (
    ExecutionRefusedError,
    ExecutionReport,
    FaultCause,
    Pair,
    ReportEntry,
    StrategyFault,
    qualified_type_name,
)
from sentaris_engine.domain.errors import EvaluationTypeError
from sentaris_engine.domain.evaluation import NotAnOutcome
from sentaris_engine.domain.parameters import Parameters
from sentaris_engine.domain.payload import FrozenMapping
from sentaris_engine.domain.result import EvaluationFailure, NoSignal, Signals
from sentaris_engine.domain.signal import Signal
from sentaris_engine.domain.strategy import StrategyIdentity
from tests.application import type_name_cases, type_name_other
from tests.domain.evaluation_helpers import raises_exactly
from tests.domain.strategy_helpers import IDENTITY, MinimalStateless

_TYPE_NAME_CASES = [
    pytest.param(cls, expected, log, id=f"{base.__name__}-{case_id}")
    for base in (object, Exception)
    for case_id, cls, expected, log in type_name_cases.type_name_cases(base)
]


@pytest.mark.parametrize(("cls", "expected", "log"), _TYPE_NAME_CASES)
def test_type_name_is_module_qualified_and_safe(cls: type, expected: str, log: list[str]) -> None:
    result = qualified_type_name(cls)
    assert type(result) is str
    assert result == expected
    assert log == []


@pytest.mark.parametrize("base", [object, Exception])
def test_same_name_in_two_modules_differs(base: type) -> None:
    [(_, here, here_expected, _)] = [case for case in type_name_cases.type_name_cases(base) if case[0] == "twin"]
    [(_, there, there_expected, _)] = type_name_other.type_name_cases(base)
    assert here.__qualname__ == there.__qualname__ == "type_name_cases.<locals>.Twin"
    assert qualified_type_name(here) == here_expected
    assert qualified_type_name(there) == there_expected
    assert here_expected != there_expected


class _StrSub(str):
    pass


def _parameters() -> Parameters:
    return Parameters({"k": 7})


def test_pair_is_validated() -> None:
    strategy = MinimalStateless()
    parameters = _parameters()
    bad_instruments: tuple[object, ...] = ("", None, 1, _StrSub("A"))
    for instrument in bad_instruments:
        raises_exactly(EvaluationTypeError, partial(Pair, instrument, strategy, parameters))  # type: ignore[arg-type]
    bad_parameters: tuple[object, ...] = ({}, None, FrozenMapping({}))
    for value in bad_parameters:
        raises_exactly(EvaluationTypeError, partial(Pair, "A", strategy, value))  # type: ignore[arg-type]

    class Untouchable(MinimalStateless):
        def __getattribute__(self, name: str) -> object:
            raise AssertionError("strategy attribute read")

        def __eq__(self, other: object) -> bool:
            raise AssertionError("strategy compared")

        def __hash__(self) -> int:
            raise AssertionError("strategy hashed")

        def __repr__(self) -> str:
            raise AssertionError("strategy repr")

    hostile = Untouchable()
    pair = Pair("A", hostile, parameters)
    assert pair.strategy is hostile
    assert pair.parameters is parameters
    assert type(repr(pair)) is str

    first = Pair("A", strategy, parameters)
    second = Pair("A", strategy, parameters)
    assert first.strategy is strategy
    assert first.parameters is parameters
    assert first != second


class _ClaimsIdentity:
    @property  # type: ignore[misc]
    def __class__(self) -> type:
        return StrategyIdentity


def _signals() -> Signals:
    return Signals((Signal("k", FrozenMapping({})),))


def test_report_types_are_validated_final_and_frozen() -> None:
    bad_causes: tuple[object, ...] = ("raised", None, 1)
    for cause in bad_causes:
        raises_exactly(EvaluationTypeError, partial(StrategyFault, cause, "x"))  # type: ignore[arg-type]
    bad_names: tuple[object, ...] = (None, 1, _StrSub("x"))
    for name in bad_names:
        raises_exactly(EvaluationTypeError, partial(StrategyFault, FaultCause.RAISED, name))  # type: ignore[arg-type]
    assert StrategyFault(FaultCause.RAISED, "").type_name == ""
    fault = StrategyFault(FaultCause.RAISED, "x")
    assert fault == StrategyFault(FaultCause.RAISED, "x")
    assert hash(fault) == hash(StrategyFault(FaultCause.RAISED, "x"))
    assert fault != StrategyFault(FaultCause.RETURNED_NON_OUTCOME, "x")

    outcome = NoSignal()
    bad_entry_instruments: tuple[object, ...] = ("", 1)
    for instrument in bad_entry_instruments:
        raises_exactly(EvaluationTypeError, partial(ReportEntry, instrument, IDENTITY, outcome))  # type: ignore[arg-type]
    bad_identities: tuple[object, ...] = (None, ("test", "1"), _ClaimsIdentity())
    for identity in bad_identities:
        raises_exactly(EvaluationTypeError, partial(ReportEntry, "A", identity, outcome))  # type: ignore[arg-type]
    bad_outcomes: tuple[object, ...] = (None, NotAnOutcome(int), NoSignal, Signal("k", FrozenMapping({})))
    for value in bad_outcomes:
        raises_exactly(EvaluationTypeError, partial(ReportEntry, "A", IDENTITY, value))  # type: ignore[arg-type]
    good_outcomes = (_signals(), NoSignal(), EvaluationFailure("f"), fault)
    for good in good_outcomes:
        assert ReportEntry("A", IDENTITY, good).outcome is good

    bad_instants: tuple[object, ...] = (-1, True, 2**53, 1.0)
    for as_of in bad_instants:
        raises_exactly(EvaluationTypeError, partial(ExecutionReport, as_of, ()))  # type: ignore[arg-type]
    entry = ReportEntry("A", IDENTITY, outcome)
    raises_exactly(EvaluationTypeError, lambda: ExecutionReport(5, [entry]))  # type: ignore[arg-type]
    raises_exactly(EvaluationTypeError, lambda: ExecutionReport(5, (entry, None)))  # type: ignore[arg-type]
    assert ExecutionReport(5, ()).entries == ()

    for final_class in (Pair, StrategyFault, ReportEntry, ExecutionReport, FaultCause):
        raises_exactly(TypeError, _subclass_of(final_class))

    instances: tuple[object, ...] = (
        Pair("A", MinimalStateless(), _parameters()),
        fault,
        entry,
        ExecutionReport(5, (entry,)),
    )
    for instance in instances:
        assert not hasattr(instance, "__dict__")
        for f in dataclasses.fields(instance):  # type: ignore[arg-type]
            raises_exactly(dataclasses.FrozenInstanceError, _assign(instance, f.name))

    assert list(FaultCause) == [FaultCause.RAISED, FaultCause.RETURNED_NON_OUTCOME]


def _subclass_of(base: type) -> Callable[[], object]:
    def define() -> type:
        class Sub(base):  # type: ignore[misc]
            pass

        return Sub

    return define


def _assign(instance: object, name: str) -> Callable[[], object]:
    return lambda: setattr(instance, name, None)


def test_refusal_error_is_its_own_class() -> None:
    assert issubclass(ExecutionRefusedError, ValueError)
    assert not issubclass(ExecutionRefusedError, EvaluationTypeError)
