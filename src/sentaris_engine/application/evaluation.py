"""Evaluate one stateless strategy on one evaluation context (DR-14, DR-26, OD-13).

The function checks that the strategy has an identity and that what it returned is one of the three outcomes. It reads
no payload and catches nothing: how a raised exception is reported next to other strategies is `execute_strategies` in
`application/execution.py` (OD-15, ADR-0002).
"""

from __future__ import annotations

from typing import cast

from sentaris_engine.domain.evaluation import (
    EvaluationContext,
    EvaluationFailure,
    NoSignal,
    Result,
    Signals,
    StatelessStrategy,
)


class StrategyContractError(Exception):
    """A strategy broke its contract: it has no valid identity or it returned something that is not a result."""


def _require_identity(value: object, name: str) -> None:
    if type(value) is not str:
        raise StrategyContractError(f"strategy {name} must be a str, got {type(value).__name__}")
    if not value:
        raise StrategyContractError(f"strategy {name} must not be empty")


def read_identity(strategy: StatelessStrategy) -> tuple[str, str]:
    """Read `strategy.id` and `strategy.version`, once each, and return them as `(id, version)`.

    Raises `StrategyContractError` if either is not an exact non-empty `str`. An error raised by reading an attribute
    propagates.
    """
    strategy_id = strategy.id
    strategy_version = strategy.version
    _require_identity(strategy_id, "id")
    _require_identity(strategy_version, "version")
    return strategy_id, strategy_version


def check_result(strategy_id: str, strategy_version: str, outcome: object) -> Result:
    """Return `outcome` if it is exactly a `Signals`, a `NoSignal` or an `EvaluationFailure`, else raise.

    Raises `StrategyContractError`, naming the strategy by the two arguments, for anything else (DR-14).
    """
    if type(outcome) not in (Signals, NoSignal, EvaluationFailure):
        raise StrategyContractError(
            f"strategy {strategy_id!r} version {strategy_version!r} returned {type(outcome).__name__}, "
            "which is not Signals, NoSignal or EvaluationFailure"
        )
    return cast(Result, outcome)


def evaluate_strategy(strategy: StatelessStrategy, context: EvaluationContext) -> Result:
    """Return the strategy's result for `context`, unchanged.

    Raises `StrategyContractError` if `strategy.id` or `strategy.version` is not an exact non-empty `str`, or if the
    outcome is not exactly a `Signals`, a `NoSignal` or an `EvaluationFailure`. An exception raised by the strategy
    propagates. A non-result is never read as "no signal" (DR-14).

    A strategy object without an `id` or `version` attribute raises `AttributeError` from the attribute read, not
    `StrategyContractError`; mypy catches that statically through `StatelessStrategy`.
    """
    strategy_id, strategy_version = read_identity(strategy)
    return check_result(strategy_id, strategy_version, strategy.evaluate(context))
