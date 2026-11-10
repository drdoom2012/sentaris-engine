"""What one evaluation takes and returns, and the contract of a stateless strategy (OD-3, OD-13, OD-14, ADR-0001).

A result is exactly one of signals, no signal or an evaluation failure (DR-14). A signal is a strategy-owned `kind` and
an immutable payload; the engine neither names nor enumerates kinds and never reads a payload (DR-23). Every type here
checks its fields by exact type at construction and raises `ValueError`; a subclass of an accepted type is rejected.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sentaris_engine.domain.market import Snapshot
from sentaris_engine.domain.parameters import Parameters
from sentaris_engine.domain.payload import Payload
from sentaris_engine.domain.timing import EpochMs, require_instant


def _require_text(value: object, name: str) -> None:
    if type(value) is not str:
        raise ValueError(f"{name} must be a str, got {type(value).__name__}")
    if not value:
        raise ValueError(f"{name} must not be empty")


@dataclass(frozen=True, slots=True)
class Signal:
    """One signal: a strategy-owned, non-empty `kind` and an immutable `Payload`."""

    kind: str
    payload: Payload

    def __post_init__(self) -> None:
        _require_text(self.kind, "kind")
        if type(self.payload) is not Payload:
            raise ValueError(f"payload must be a Payload, got {type(self.payload).__name__}")


@dataclass(frozen=True, slots=True)
class Signals:
    """The signals of one evaluation: a non-empty `tuple` in the strategy's order, which is never sorted."""

    signals: tuple[Signal, ...]

    def __post_init__(self) -> None:
        if type(self.signals) is not tuple:
            raise ValueError(f"signals must be a tuple, got {type(self.signals).__name__}")
        if not self.signals:
            raise ValueError("signals must be a non-empty tuple; no signal is NoSignal")
        for signal in self.signals:
            if type(signal) is not Signal:
                raise ValueError(f"signals must hold Signal objects, got {type(signal).__name__}")


@dataclass(frozen=True, slots=True)
class NoSignal:
    """The strategy evaluated and found nothing to signal."""


@dataclass(frozen=True, slots=True)
class EvaluationFailure:
    """The strategy could not evaluate. `code` is a non-empty machine-readable string; the taxonomy is open (OD-3)."""

    code: str

    def __post_init__(self) -> None:
        _require_text(self.code, "code")


type Result = Signals | NoSignal | EvaluationFailure


@dataclass(frozen=True, slots=True)
class EvaluationContext:
    """Everything a stateless strategy may read: the snapshot, its parameters and the instant `as_of` (DR-26)."""

    snapshot: Snapshot
    parameters: Parameters
    as_of: EpochMs

    def __post_init__(self) -> None:
        if type(self.snapshot) is not Snapshot:
            raise ValueError(f"snapshot must be a Snapshot, got {type(self.snapshot).__name__}")
        if type(self.parameters) is not Parameters:
            raise ValueError(f"parameters must be a Parameters, got {type(self.parameters).__name__}")
        require_instant(self.as_of, "as_of")


class StatelessStrategy(Protocol):
    """A strategy of the form `context -> result` (DR-26). Pure: it reads only the context (DR-08, DR-09).

    `id` and `version` are read-only, non-empty strings with no imposed format; a change in behavior is a new version
    (OD-13). A plain attribute or a property satisfies them.
    """

    @property
    def id(self) -> str: ...

    @property
    def version(self) -> str: ...

    def evaluate(self, context: EvaluationContext) -> Result: ...
