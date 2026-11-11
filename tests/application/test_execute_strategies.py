import itertools
from collections.abc import Iterator
from decimal import Decimal
from typing import Any, cast

import pytest

from sentaris_engine.application.evaluation import StrategyContractError
from sentaris_engine.application.execution import (
    ExecutionReport,
    StrategyRaised,
    StrategyReport,
    execute_strategies,
)
from sentaris_engine.domain.evaluation import (
    EvaluationContext,
    EvaluationFailure,
    NoSignal,
    StatelessStrategy,
)
from sentaris_engine.domain.market import Candle, CandleSeries, Snapshot
from sentaris_engine.domain.parameters import Parameters
from tests.support.probes import (
    BrokenProbe,
    CountingIdentityProbe,
    FailingStrError,
    LastCloseProbe,
    MutatingProbe,
    RaisingProbe,
    RecordingProbe,
    RecordingRaisingProbe,
    ScriptedProbe,
)

FIVE_MINUTES = 300_000
AS_OF = 1_700_000_000_000
OTHER_AS_OF = AS_OF + FIVE_MINUTES

type Pair = tuple[StatelessStrategy, EvaluationContext]


class StrSubclass(str):
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


CANDLES = (candle(AS_OF - FIVE_MINUTES, Decimal("64210.5")),)


def new_snapshot() -> Snapshot:
    return Snapshot.of([CandleSeries.of(FIVE_MINUTES, CANDLES)])


SNAPSHOT = new_snapshot()


def context_for(
    snapshot: Snapshot | None = None, parameters: dict[str, object] | None = None, as_of: int = AS_OF
) -> EvaluationContext:
    return EvaluationContext(SNAPSHOT if snapshot is None else snapshot, Parameters.of(parameters or {}), as_of)


CONTEXT = context_for()


def recording(strategy_id: str, version: str, seen: list[EvaluationContext] | None = None) -> RecordingProbe:
    return RecordingProbe(strategy_id, version, NoSignal(), [] if seen is None else seen)


def run(*strategies: StatelessStrategy) -> ExecutionReport:
    return execute_strategies([(strategy, CONTEXT) for strategy in strategies])


def test_report_order_does_not_depend_on_registration_order() -> None:
    probes = {
        ("b", "1"): ScriptedProbe("b", "1", EvaluationFailure("b1")),
        ("a", "2"): ScriptedProbe("a", "2", EvaluationFailure("a2")),
        ("a", "1"): ScriptedProbe("a", "1", EvaluationFailure("a1")),
        ("c", "1"): ScriptedProbe("c", "1", EvaluationFailure("c1")),
    }
    expected = ExecutionReport(
        (
            StrategyReport("a", "1", EvaluationFailure("a1")),
            StrategyReport("a", "2", EvaluationFailure("a2")),
            StrategyReport("b", "1", EvaluationFailure("b1")),
            StrategyReport("c", "1", EvaluationFailure("c1")),
        )
    )
    permutations = list(itertools.permutations(probes.values()))
    assert len(permutations) == 24
    for order in permutations:
        assert execute_strategies([(probe, CONTEXT) for probe in order]) == expected


def test_order_is_by_code_point_then_version() -> None:
    report = run(*(ScriptedProbe(i, "1", NoSignal()) for i in ("a", "Z", "é", "z")))
    assert [entry.strategy_id for entry in report.entries] == ["Z", "a", "z", "é"]
    versions = run(ScriptedProbe("a", "9", NoSignal()), ScriptedProbe("a", "10", NoSignal()))
    assert [entry.strategy_version for entry in versions.entries] == ["10", "9"]


def test_each_strategy_gets_its_own_context() -> None:
    snapshot = new_snapshot()
    identities = [("b", "1"), ("a", "2"), ("a", "1"), ("c", "1")]
    probes = [recording(strategy_id, version) for strategy_id, version in identities]
    contexts = [context_for(snapshot, {"n": i}) for i in range(len(probes))]
    assert execute_strategies(zip(probes, contexts, strict=True)).entries
    for probe, own_context in zip(probes, contexts, strict=True):
        assert len(probe.seen) == 1
        assert probe.seen[0] is own_context
        assert probe.seen[0].snapshot is snapshot
        assert probe.seen[0].parameters == own_context.parameters


def test_strategies_run_in_sorted_order() -> None:
    identities = [("b", "1"), ("a", "2"), ("a", "1"), ("c", "1")]
    sorted_identities = sorted(identities)
    for order in itertools.permutations(identities):
        seen: list[EvaluationContext] = []
        contexts = {identity: context_for(parameters={"n": i}) for i, identity in enumerate(identities)}
        pairs: list[Pair] = [(recording(sid, version, seen), contexts[(sid, version)]) for sid, version in order]
        execute_strategies(pairs)
        assert seen == [contexts[identity] for identity in sorted_identities]


def test_raising_strategy_does_not_change_the_other_entries() -> None:
    healthy_entry = execute_strategies([(LastCloseProbe("m", "1"), CONTEXT)]).entries[0]
    assert type(healthy_entry.outcome) is not StrategyRaised
    raising_first = run(RaisingProbe("a", "1", ValueError("x")), LastCloseProbe("m", "1"))
    assert raising_first.entries == (StrategyReport("a", "1", StrategyRaised("ValueError")), healthy_entry)
    raising_last = run(LastCloseProbe("m", "1"), RaisingProbe("z", "1", ValueError("x")))
    assert raising_last.entries == (healthy_entry, StrategyReport("z", "1", StrategyRaised("ValueError")))


def test_raised_exception_is_reported_by_type_name_only() -> None:
    report = run(RaisingProbe("a", "1", ValueError("secret-token-123")))
    assert "secret-token-123" not in repr(report)
    assert report.entries[0].outcome == StrategyRaised("ValueError")


def test_nested_exception_is_reported_by_qualified_name() -> None:
    class Outer:
        class Err(Exception):
            pass

    report = run(RaisingProbe("a", "1", Outer.Err("x")))
    assert report.entries[0].outcome == StrategyRaised(
        "test_nested_exception_is_reported_by_qualified_name.<locals>.Outer.Err"
    )


def test_exception_with_failing_str_is_reported() -> None:
    report = run(RaisingProbe("a", "1", FailingStrError()))
    assert report.entries[0].outcome == StrategyRaised("FailingStrError")


def test_contract_breach_in_a_result_is_reported() -> None:
    healthy_entry = execute_strategies([(LastCloseProbe("m", "1"), CONTEXT)]).entries[0]
    report = run(BrokenProbe("a", "1", None), LastCloseProbe("m", "1"))
    assert report.entries == (StrategyReport("a", "1", StrategyRaised("StrategyContractError")), healthy_entry)


def test_strategy_raised_is_not_an_evaluation_failure() -> None:
    report = run(ScriptedProbe("a", "1", EvaluationFailure("c")), RaisingProbe("b", "1", RuntimeError("x")))
    assert len(report.entries) == 2
    assert report.entries[0].outcome == EvaluationFailure("c")
    assert type(report.entries[0].outcome) is EvaluationFailure
    assert type(report.entries[1].outcome) is StrategyRaised


def test_mutating_strategy_is_reported_and_changes_nothing() -> None:
    snapshot = new_snapshot()
    shared = context_for(snapshot)
    healthy_entry = execute_strategies([(LastCloseProbe("m", "1"), CONTEXT)]).entries[0]
    report = execute_strategies([(MutatingProbe("a", "1"), shared), (LastCloseProbe("m", "1"), shared)])
    assert report.entries[0] == StrategyReport("a", "1", StrategyRaised("FrozenInstanceError"))
    assert report.entries[1] == healthy_entry
    assert snapshot == new_snapshot()
    assert shared.snapshot is snapshot


def test_base_exception_propagates() -> None:
    after = recording("b", "1")
    with pytest.raises(KeyboardInterrupt):
        run(RaisingProbe("a", "1", cast(Any, KeyboardInterrupt())), after)
    assert after.seen == []


def test_duplicate_identity_is_refused_before_anything_runs() -> None:
    for order in itertools.permutations([("a", "1"), ("a", "1"), ("b", "1")]):
        probes = [recording(strategy_id, version) for strategy_id, version in order]
        with pytest.raises(ValueError, match=r"'a'"):
            run(*probes)
        assert all(probe.seen == [] for probe in probes)
    assert len(run(recording("a", "1"), recording("a", "2")).entries) == 2


@pytest.mark.parametrize(
    "invalid",
    [
        pytest.param(("b", ""), id="empty-version"),
        pytest.param((StrSubclass("z"), "1"), id="str-subclass-id"),
        pytest.param(("b", cast(Any, 5)), id="int-version"),
    ],
)
@pytest.mark.parametrize("invalid_first", [True, False])
def test_invalid_identity_is_refused_before_anything_runs(invalid: tuple[str, str], invalid_first: bool) -> None:
    healthy = recording("a", "1")
    broken = recording(*invalid)
    with pytest.raises(StrategyContractError):
        run(*((broken, healthy) if invalid_first else (healthy, broken)))
    assert healthy.seen == []
    assert broken.seen == []


def test_empty_id_that_sorts_first_is_refused() -> None:
    healthy = recording("a", "1")
    broken = recording("", "1")
    with pytest.raises(StrategyContractError):
        run(healthy, broken)
    assert healthy.seen == []
    assert broken.seen == []


def test_identity_is_read_once() -> None:
    counting = CountingIdentityProbe()
    report = run(recording("a", "1"), counting, recording("z", "1"))
    assert [entry.strategy_id for entry in report.entries] == ["a", "counted", "z"]
    assert counting.id_reads == 1
    assert counting.version_reads == 1


def test_differing_as_of_is_refused() -> None:
    other = context_for(as_of=OTHER_AS_OF)
    for first_is_a in (True, False):
        a = recording("a", "1")
        b = recording("b", "1")
        pairs: list[Pair] = [(a, CONTEXT), (b, other)]
        with pytest.raises(ValueError, match="as_of"):
            execute_strategies(pairs if first_is_a else pairs[::-1])
        assert a.seen == []
        assert b.seen == []


def test_wrong_context_type_is_refused() -> None:
    for first_is_a in (True, False):
        a = recording("a", "1")
        b = recording("b", "1")
        pairs: list[Pair] = [(a, CONTEXT), (b, cast(Any, object()))]
        with pytest.raises(ValueError, match="EvaluationContext"):
            execute_strategies(pairs if first_is_a else pairs[::-1])
        assert a.seen == []
        assert b.seen == []


def test_first_problem_in_the_check_order_wins() -> None:
    other = context_for(as_of=OTHER_AS_OF)
    with pytest.raises(StrategyContractError):
        execute_strategies([(recording("a", "1"), CONTEXT), (recording("", "1"), other)])
    with pytest.raises(ValueError, match="as_of"):
        execute_strategies([(recording("a", "1"), CONTEXT), (recording("a", "1"), other)])


def test_checks_per_pair_in_input_order_come_before_checks_across_pairs() -> None:
    bad_identity: Pair = (recording("", "1"), CONTEXT)
    bad_context: Pair = (recording("b", "1"), cast(Any, object()))
    with pytest.raises(StrategyContractError):
        execute_strategies([bad_identity, bad_context])
    with pytest.raises(ValueError, match="EvaluationContext"):
        execute_strategies([bad_context, bad_identity])


def test_empty_input_gives_an_empty_report() -> None:
    assert execute_strategies(()) == ExecutionReport(())


def test_input_may_be_a_one_shot_iterator() -> None:
    pairs: tuple[Pair, ...] = (
        (ScriptedProbe("b", "1", NoSignal()), CONTEXT),
        (ScriptedProbe("a", "1", EvaluationFailure("x")), CONTEXT),
    )

    def generate() -> Iterator[Pair]:
        yield from pairs

    assert execute_strategies(generate()) == execute_strategies(pairs)
    assert len(execute_strategies(pairs).entries) == 2


def test_list_changed_after_the_call_does_not_change_the_report() -> None:
    pairs: list[Pair] = [(ScriptedProbe("a", "1", NoSignal()), CONTEXT)]
    report = execute_strategies(pairs)
    pairs.append((ScriptedProbe("b", "1", NoSignal()), CONTEXT))
    assert report == ExecutionReport((StrategyReport("a", "1", NoSignal()),))


def test_each_strategy_runs_once() -> None:
    probes = [recording("a", "1"), recording("b", "1"), recording("c", "1")]
    raiser_seen: list[EvaluationContext] = []
    report = run(*probes, RecordingRaisingProbe("r", "1", ValueError("x"), raiser_seen))
    assert len(report.entries) == 4
    assert all(len(probe.seen) == 1 for probe in probes)
    assert len(raiser_seen) == 1
