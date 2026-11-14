"""Test strategies and builders of the SE-4 tests (strategies live under `tests/` only)."""

from collections.abc import Sequence

from sentaris_engine.domain.context import EvaluationContext
from sentaris_engine.domain.declaration import Declaration
from sentaris_engine.domain.evaluation import evaluate_stateless
from sentaris_engine.domain.parameters import Parameters
from sentaris_engine.domain.payload import FrozenMapping
from sentaris_engine.domain.result import NoSignal, Result, Signals
from sentaris_engine.domain.signal import Signal
from sentaris_engine.domain.strategy import StatefulStrategy, StatelessStrategy, StateTransition, StrategyIdentity
from tests.domain.row_builders import snapshot

IDENTITY = StrategyIdentity("test", "1")
EMPTY_DECLARATION = Declaration(())


class MinimalStateless(StatelessStrategy):
    identity = IDENTITY

    def evaluate(self, context: EvaluationContext) -> Result:
        return NoSignal()

    def declare(self, parameters: Parameters) -> Declaration:
        return EMPTY_DECLARATION


class MinimalStateful(StatefulStrategy):
    identity = IDENTITY

    def evaluate(self, context: EvaluationContext, previous_state: object) -> StateTransition:
        return StateTransition(NoSignal(), previous_state)

    def declare(self, parameters: Parameters) -> Declaration:
        return EMPTY_DECLARATION


def make_context(as_of: int = 10_000_000) -> EvaluationContext:
    """Build a new context; every call gives new objects with the same field values."""
    return EvaluationContext(snapshot(as_of), Parameters({"k": 7}), as_of)


class ReturningStrategy(StatelessStrategy):
    """Returns the given value on every call, which may be a non-outcome, and records each context."""

    identity = IDENTITY

    def __init__(self, value: object) -> None:
        self.value = value
        self.calls: list[EvaluationContext] = []

    def evaluate(self, context: EvaluationContext) -> Result:
        self.calls.append(context)
        return self.value  # type: ignore[return-value]

    def declare(self, parameters: Parameters) -> Declaration:
        return EMPTY_DECLARATION


class RaisingStrategy(StatelessStrategy):
    """Raises the given object outside any `except` block, so its `__context__` stays as set, and records each context."""

    identity = IDENTITY

    def __init__(self, exc: BaseException) -> None:
        self.exc = exc
        self.calls: list[EvaluationContext] = []

    def evaluate(self, context: EvaluationContext) -> Result:
        self.calls.append(context)
        raise self.exc

    def declare(self, parameters: Parameters) -> Declaration:
        return EMPTY_DECLARATION


class ContextSignalStrategy(StatelessStrategy):
    """Deterministic: one signal built from the context's `as_of` and parameter `k`; records each context."""

    identity = IDENTITY

    def __init__(self) -> None:
        self.calls: list[EvaluationContext] = []

    def evaluate(self, context: EvaluationContext) -> Result:
        self.calls.append(context)
        return Signals((Signal("seen", FrozenMapping({"as_of": context.as_of, "k": context.parameters["k"]})),))

    def declare(self, parameters: Parameters) -> Declaration:
        return EMPTY_DECLARATION


class VaryingStrategy(StatelessStrategy):
    """Not deterministic: the payload holds a counter incremented on each call."""

    identity = IDENTITY

    def __init__(self) -> None:
        self.count = 0

    def evaluate(self, context: EvaluationContext) -> Result:
        self.count += 1
        return Signals((Signal("count", FrozenMapping({"n": self.count})),))

    def declare(self, parameters: Parameters) -> Declaration:
        return EMPTY_DECLARATION


def check_deterministic(strategy: StatelessStrategy, contexts: Sequence[EvaluationContext], repeats: int = 3) -> None:
    """Evaluate each context `repeats` times; raise `AssertionError` unless every result equals the first one."""
    results = [evaluate_stateless(strategy, context) for context in contexts for _ in range(repeats)]
    first = results[0]
    for result in results:
        if result != first:
            raise AssertionError("results differ between evaluations")
