"""Evaluate one stateless strategy on one evaluation context (DR-14, DR-26, OD-13).

The function checks that the strategy has an identity and that what it returned is one of the three outcomes. It reads
no payload and catches nothing: how a raised exception is reported next to other strategies is OD-15.
"""

from __future__ import annotations

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


def evaluate_strategy(strategy: StatelessStrategy, context: EvaluationContext) -> Result:
    """Return the strategy's result for `context`, unchanged.

    Raises `StrategyContractError` if `strategy.id` or `strategy.version` is not an exact non-empty `str`, or if the
    outcome is not exactly a `Signals`, a `NoSignal` or an `EvaluationFailure`. An exception raised by the strategy
    propagates. A non-result is never read as "no signal" (DR-14).
    """
    _require_identity(strategy.id, "id")
    _require_identity(strategy.version, "version")
    outcome = strategy.evaluate(context)
    if type(outcome) not in (Signals, NoSignal, EvaluationFailure):
        raise StrategyContractError(
            f"strategy {strategy.id!r} version {strategy.version!r} returned {type(outcome).__name__}, "
            "which is not Signals, NoSignal or EvaluationFailure"
        )
    return outcome
