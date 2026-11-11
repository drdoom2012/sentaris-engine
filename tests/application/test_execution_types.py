from typing import Any, cast

import pytest

from sentaris_engine.application.execution import ExecutionReport, StrategyRaised, StrategyReport
from sentaris_engine.domain.evaluation import EvaluationFailure, NoSignal, Signal, Signals
from sentaris_engine.domain.payload import Payload


class StrSubclass(str):
    pass


class SignalsSubclass(Signals):
    pass


class NoSignalSubclass(NoSignal):
    pass


class EvaluationFailureSubclass(EvaluationFailure):
    pass


class StrategyRaisedSubclass(StrategyRaised):
    pass


class StrategyReportSubclass(StrategyReport):
    pass


def _report(strategy_id: str, version: str) -> StrategyReport:
    return StrategyReport(strategy_id, version, NoSignal())


def test_strategy_raised_requires_a_non_empty_exact_str() -> None:
    assert StrategyRaised("ValueError").error_type == "ValueError"
    for bad in ("", 1, None, StrSubclass("E")):
        with pytest.raises(ValueError, match="error_type"):
            StrategyRaised(cast(Any, bad))


def test_strategy_report_requires_exact_identity_and_outcome() -> None:
    signals = Signals((Signal("k", Payload.of({})),))
    for outcome in (signals, NoSignal(), EvaluationFailure("c"), StrategyRaised("E")):
        assert StrategyReport("a", "1", outcome).outcome == outcome

    for bad in ("", 1, None, StrSubclass("a")):
        with pytest.raises(ValueError, match="strategy_id"):
            StrategyReport(cast(Any, bad), "1", NoSignal())
        with pytest.raises(ValueError, match="strategy_version"):
            StrategyReport("a", cast(Any, bad), NoSignal())

    subclassed = (
        SignalsSubclass(signals.signals),
        NoSignalSubclass(),
        EvaluationFailureSubclass("c"),
        StrategyRaisedSubclass("E"),
    )
    for bad_outcome in (None, "NoSignal", *subclassed):
        with pytest.raises(ValueError, match="outcome"):
            StrategyReport("a", "1", cast(Any, bad_outcome))


def test_strategy_raised_is_not_an_evaluation_failure() -> None:
    assert StrategyReport("a", "1", StrategyRaised("E")) != StrategyReport("a", "1", EvaluationFailure("E"))


def test_execution_report_requires_strictly_ascending_exact_entries() -> None:
    assert ExecutionReport(()).entries == ()
    ascending = (_report("a", "1"), _report("a", "2"), _report("b", "1"))
    assert ExecutionReport(ascending).entries == ascending

    with pytest.raises(ValueError, match="ascending"):
        ExecutionReport((_report("a", "2"), _report("a", "1")))
    with pytest.raises(ValueError, match="ascending"):
        ExecutionReport((_report("a", "1"), _report("a", "1")))
    with pytest.raises(ValueError, match="tuple"):
        ExecutionReport(cast(Any, [_report("a", "1")]))
    with pytest.raises(ValueError, match="StrategyReport"):
        ExecutionReport(cast(Any, (_report("a", "1"), "b")))
    with pytest.raises(ValueError, match="StrategyReport"):
        ExecutionReport((StrategyReportSubclass("a", "1", NoSignal()),))


def test_report_values_are_immutable_and_comparable() -> None:
    report = _report("a", "1")
    with pytest.raises(AttributeError):
        cast(Any, report).strategy_id = "b"
    with pytest.raises(AttributeError):
        cast(Any, StrategyRaised("E")).error_type = "F"
    execution = ExecutionReport((report,))
    with pytest.raises(AttributeError):
        cast(Any, execution).entries = ()

    assert report == _report("a", "1")
    assert hash(report) == hash(_report("a", "1"))
    assert ExecutionReport((report,)) == ExecutionReport((_report("a", "1"),))
    assert hash(ExecutionReport((report,))) == hash(ExecutionReport((_report("a", "1"),)))
