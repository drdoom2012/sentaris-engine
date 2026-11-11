"""The report of executing several stateless strategies at one instant (OD-15, ADR-0002, DR-10, DR-14, DR-22).

An execution reports one entry per strategy, each exactly one of signals, no signal, an evaluation failure or a raise,
in ascending `(strategy_id, strategy_version)` order. A raise is its own outcome and is never an `EvaluationFailure`
(DR-14): the strategy did not return a failure, it broke. A raise is reported by the exception's type name only; an
exception's message and traceback are never stored. Every type here checks its fields by exact type at construction and
raises `ValueError`; a subclass of an accepted type is rejected.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from itertools import pairwise

from sentaris_engine.application.evaluation import check_result, read_identity
from sentaris_engine.domain.evaluation import (
    EvaluationContext,
    EvaluationFailure,
    NoSignal,
    Signals,
    StatelessStrategy,
)


def _require_text(value: object, name: str) -> None:
    if type(value) is not str:
        raise ValueError(f"{name} must be a str, got {type(value).__name__}")
    if not value:
        raise ValueError(f"{name} must not be empty")


@dataclass(frozen=True, slots=True)
class StrategyRaised:
    """The strategy raised an `Exception`. `error_type` is the exception's type name; its message is never kept."""

    error_type: str

    def __post_init__(self) -> None:
        _require_text(self.error_type, "error_type")


type StrategyOutcome = Signals | NoSignal | EvaluationFailure | StrategyRaised


@dataclass(frozen=True, slots=True)
class StrategyReport:
    """What one strategy, identified by `strategy_id` and `strategy_version`, produced in one execution."""

    strategy_id: str
    strategy_version: str
    outcome: StrategyOutcome

    def __post_init__(self) -> None:
        _require_text(self.strategy_id, "strategy_id")
        _require_text(self.strategy_version, "strategy_version")
        if type(self.outcome) not in (Signals, NoSignal, EvaluationFailure, StrategyRaised):
            raise ValueError(
                "outcome must be Signals, NoSignal, EvaluationFailure or StrategyRaised, "
                f"got {type(self.outcome).__name__}"
            )


@dataclass(frozen=True, slots=True)
class ExecutionReport:
    """The entries of one execution: a `tuple` of `StrategyReport`, strictly ascending by `(id, version)`.

    Strictly ascending means no strategy appears twice. An empty report is valid: no strategy was given.
    """

    entries: tuple[StrategyReport, ...]

    def __post_init__(self) -> None:
        if type(self.entries) is not tuple:
            raise ValueError(f"entries must be a tuple, got {type(self.entries).__name__}")
        for entry in self.entries:
            if type(entry) is not StrategyReport:
                raise ValueError(f"entries must hold StrategyReport objects, got {type(entry).__name__}")
        for previous, current in pairwise(self.entries):
            if not (
                (previous.strategy_id, previous.strategy_version) < (current.strategy_id, current.strategy_version)
            ):
                raise ValueError("entries must be strictly ascending by (strategy_id, strategy_version)")


@dataclass(frozen=True, slots=True)
class _Entry:
    strategy_id: str
    strategy_version: str
    strategy: StatelessStrategy
    context: EvaluationContext


def _read_entry(strategy: StatelessStrategy, context: EvaluationContext) -> _Entry:
    if type(context) is not EvaluationContext:
        raise ValueError(f"context must be an EvaluationContext, got {type(context).__name__}")
    strategy_id, strategy_version = read_identity(strategy)
    return _Entry(strategy_id, strategy_version, strategy, context)


def execute_strategies(entries: Iterable[tuple[StatelessStrategy, EvaluationContext]]) -> ExecutionReport:
    """Evaluate each strategy on its own context, one after another, and report one entry per strategy.

    The report lists the entries in ascending `(id, version)` order, compared by code point, whatever the order of
    `entries` (DR-10). `entries` is read once, so a one-shot iterator is fine. An empty input gives an empty report.
    Every strategy's `id` and `version` is read once, and one strategy's outcome never changes another's (DR-22).

    Before anything runs, the input is checked, and the first problem found is raised. First, for each pair in input
    order: a context that is not exactly an `EvaluationContext` raises `ValueError`, then an `id` or `version` that is
    not an exact non-empty `str` raises `StrategyContractError` (an error from reading the attribute propagates).
    Then, across all pairs: contexts with different `as_of` raise `ValueError`, then two strategies with the same
    `(id, version)` raise `ValueError`.

    Then each strategy is evaluated. An `Exception` it raises, including the `StrategyContractError` for a result that
    is not exactly signals, no signal or an evaluation failure, is caught for that strategy and reported as
    `StrategyRaised` with the exception's type name; the message is never read. A `BaseException` that is not an
    `Exception`, such as `KeyboardInterrupt`, propagates and no report is returned.
    """
    read = [_read_entry(strategy, context) for strategy, context in tuple(entries)]
    if len({entry.context.as_of for entry in read}) > 1:
        raise ValueError("all evaluation contexts of one execution must have the same as_of")
    read.sort(key=lambda entry: (entry.strategy_id, entry.strategy_version))
    for previous, current in pairwise(read):
        if (previous.strategy_id, previous.strategy_version) == (current.strategy_id, current.strategy_version):
            raise ValueError(f"duplicate strategy identity ({current.strategy_id!r}, {current.strategy_version!r})")
    reports: list[StrategyReport] = []
    for entry in read:
        outcome: StrategyOutcome
        try:
            outcome = check_result(entry.strategy_id, entry.strategy_version, entry.strategy.evaluate(entry.context))
        except Exception as error:  # noqa: BLE001 -- ADR-0002: one strategy's Exception is reported, not propagated
            outcome = StrategyRaised(type(error).__qualname__)
        reports.append(StrategyReport(entry.strategy_id, entry.strategy_version, outcome))
    return ExecutionReport(tuple(reports))
