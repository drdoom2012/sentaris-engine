import itertools
from decimal import Decimal
from typing import Any, cast

import pytest

from sentaris_engine.application.evaluation import StrategyContractError, evaluate_strategy
from sentaris_engine.domain.evaluation import (
    EvaluationContext,
    EvaluationFailure,
    NoSignal,
    Signal,
    Signals,
)
from sentaris_engine.domain.market import Candle, CandleSeries, Snapshot
from sentaris_engine.domain.parameters import Parameters
from sentaris_engine.domain.payload import Payload
from tests.support.probes import BrokenProbe, LastCloseProbe, MutatingProbe, RaisingProbe, ScriptedProbe

FIVE_MINUTES = 300_000
AS_OF = 1_700_000_000_000
LAST_CLOSE = Decimal("64210.123456789012345678")
EXPECTED_BYTES = b'{"$map":{"as_of":1700000000000,"close":{"$decimal":"64210.123456789012345678"},"count":3}}'


class StrSubclass(str):
    pass


class SignalsSubclass(Signals):
    pass


class NoSignalSubclass(NoSignal):
    pass


class FailureSubclass(EvaluationFailure):
    pass


def candle(open_time_ms: int, close: Decimal) -> Candle:
    return Candle(
        open_time_ms=open_time_ms,
        open=Decimal("1.5"),
        high=Decimal(2),
        low=Decimal(1),
        close=close,
        volume=Decimal(10),
        turnover=None,
        conflicted=False,
    )


FIXTURE_CANDLES = (
    candle(AS_OF - 3 * FIVE_MINUTES, Decimal("64000.5")),
    candle(AS_OF - 2 * FIVE_MINUTES, Decimal("64100.25")),
    candle(AS_OF - FIVE_MINUTES, LAST_CLOSE),
)


def context_for(
    snapshot: Snapshot | None = None, parameters: dict[str, object] | None = None, as_of: int = AS_OF
) -> EvaluationContext:
    if snapshot is None:
        snapshot = Snapshot.of([CandleSeries.of(FIVE_MINUTES, FIXTURE_CANDLES)])
    return EvaluationContext(snapshot, Parameters.of(parameters or {}), as_of)


def test_each_outcome_is_returned_unchanged() -> None:
    signals = Signals((Signal("probe.any", Payload.of({"n": 1})),))
    outcomes = (signals, NoSignal(), EvaluationFailure("x"))
    returned = [evaluate_strategy(ScriptedProbe("scripted", "1", outcome), context_for()) for outcome in outcomes]
    assert [type(r) for r in returned] == [Signals, NoSignal, EvaluationFailure]
    assert len({type(r) for r in returned}) == 3
    for outcome, result in zip(outcomes, returned, strict=True):
        assert result is outcome


def test_probe_evaluated_end_to_end_from_fixture_snapshot() -> None:
    result = evaluate_strategy(LastCloseProbe("probe.last_close", "1"), context_for())
    assert isinstance(result, Signals)
    assert len(result.signals) == 1
    signal = result.signals[0]
    assert signal.kind == "probe.last_close"
    assert signal.payload.canonical() == EXPECTED_BYTES
    assert b"64210.123456789012345678" in signal.payload.canonical()


def test_repeated_evaluation_is_deeply_equal() -> None:
    context = context_for()
    probe = LastCloseProbe("probe.last_close", "1")
    first = evaluate_strategy(probe, context)
    second = evaluate_strategy(probe, context)
    assert first == second
    assert isinstance(first, Signals)
    assert isinstance(second, Signals)
    assert first.signals[0].payload.canonical() == second.signals[0].payload.canonical() == EXPECTED_BYTES


def test_shuffled_candle_order_gives_the_same_result() -> None:
    probe = LastCloseProbe("probe.last_close", "1")
    baseline = evaluate_strategy(probe, context_for())
    permutations = list(itertools.permutations(FIXTURE_CANDLES))
    assert len(permutations) == 6
    assert any(order != FIXTURE_CANDLES for order in permutations)
    for order in permutations:
        snapshot = Snapshot.of([CandleSeries.of(FIVE_MINUTES, order)])
        assert evaluate_strategy(probe, context_for(snapshot)) == baseline


def test_probe_fails_when_series_is_missing() -> None:
    probe = LastCloseProbe("probe.last_close", "1")
    empty_snapshot = Snapshot.of([])
    empty_series = Snapshot.of([CandleSeries.of(FIVE_MINUTES, [])])
    other_timeframe = Snapshot.of([CandleSeries.of(60_000, FIXTURE_CANDLES)])
    for snapshot in (empty_snapshot, empty_series, other_timeframe):
        result = evaluate_strategy(probe, context_for(snapshot))
        assert result == EvaluationFailure("series_missing")
        assert type(result) is EvaluationFailure


@pytest.mark.parametrize("limit", [0, -1, True, "3"])
def test_invalid_parameters_are_a_failure_not_an_exception(limit: object) -> None:
    result = evaluate_strategy(LastCloseProbe("probe.last_close", "1"), context_for(parameters={"limit": limit}))
    assert result == EvaluationFailure("invalid_parameters")


def test_valid_limit_is_accepted() -> None:
    result = evaluate_strategy(LastCloseProbe("probe.last_close", "1"), context_for(parameters={"limit": 3}))
    assert type(result) is Signals


@pytest.mark.parametrize(
    "returned",
    [
        pytest.param(None, id="none"),
        pytest.param({}, id="dict"),
        pytest.param([], id="list"),
        pytest.param("no signal", id="str"),
        pytest.param(False, id="false"),
        pytest.param(Signal("probe.any", Payload.of({})), id="bare-signal"),
        pytest.param(SignalsSubclass((Signal("probe.any", Payload.of({})),)), id="signals-subclass"),
        pytest.param(NoSignalSubclass(), id="no-signal-subclass"),
        pytest.param(FailureSubclass("x"), id="failure-subclass"),
    ],
)
def test_non_result_is_contract_error(returned: object) -> None:
    with pytest.raises(StrategyContractError):
        evaluate_strategy(BrokenProbe("broken", "1", returned), context_for())


@pytest.mark.parametrize(
    ("strategy_id", "version"),
    [
        pytest.param("", "1", id="empty-id"),
        pytest.param("probe", "", id="empty-version"),
        pytest.param(5, "1", id="int-id"),
        pytest.param("probe", None, id="none-version"),
        pytest.param(StrSubclass("probe"), "1", id="str-subclass-id"),
        pytest.param("probe", StrSubclass("1"), id="str-subclass-version"),
    ],
)
def test_invalid_identity_is_contract_error(strategy_id: object, version: object) -> None:
    probe = ScriptedProbe(cast(Any, strategy_id), cast(Any, version), NoSignal())
    with pytest.raises(StrategyContractError):
        evaluate_strategy(probe, context_for())


def test_strategy_exception_is_not_swallowed() -> None:
    error = RuntimeError("boom")
    with pytest.raises(RuntimeError) as raised:
        evaluate_strategy(RaisingProbe("raising", "1", error), context_for())
    assert raised.value is error


def test_snapshot_cannot_be_mutated_by_a_strategy() -> None:
    context = context_for()
    before = context.snapshot
    with pytest.raises((AttributeError, TypeError)):
        evaluate_strategy(MutatingProbe("mutating", "1"), context)
    assert context.snapshot is before
    assert context.snapshot == Snapshot.of([CandleSeries.of(FIVE_MINUTES, FIXTURE_CANDLES)])
    assert len(context.snapshot.series) == 1
