"""Test strategies and builders of the SE-5 execution tests (strategies live under `tests/` only)."""

from typing import Final

from sentaris_engine.domain.context import EvaluationContext
from sentaris_engine.domain.parameters import Parameters
from sentaris_engine.domain.result import NoSignal, Result
from sentaris_engine.domain.snapshot import Snapshot
from sentaris_engine.domain.strategy import StatelessStrategy, StrategyIdentity

Call = tuple[StrategyIdentity, EvaluationContext]

_NO_SIGNAL: Final = NoSignal()


class RecordingStrategy(StatelessStrategy):
    """Logs each call as `(identity, context)`; returns `outcome` (any object), or raises it when `raises` is true.

    The `identity` property counts its reads in `identity_reads` and records the log length at each read in
    `read_log_lengths`.
    """

    def __init__(
        self,
        identity: StrategyIdentity,
        log: list[Call],
        outcome: object = _NO_SIGNAL,
        *,
        raises: bool = False,
    ) -> None:
        self._identity = identity
        self.log = log
        self.outcome = outcome
        self.raises = raises
        self.identity_reads = 0
        self.read_log_lengths: list[int] = []

    @property
    def identity(self) -> StrategyIdentity:
        self.identity_reads += 1
        self.read_log_lengths.append(len(self.log))
        return self._identity

    def evaluate(self, context: EvaluationContext) -> Result:
        self.log.append((self._identity, context))
        if self.raises:
            raise self.outcome  # type: ignore[misc]
        return self.outcome  # type: ignore[return-value]


def params(k: int = 1) -> Parameters:
    return Parameters({"k": k})


def instrument_of(context: EvaluationContext, snapshots: dict[str, Snapshot]) -> str:
    """The key whose snapshot `is` the context's snapshot (found by `is`, for test assertions)."""
    [key] = [key for key, value in snapshots.items() if value is context.snapshot]
    return key
