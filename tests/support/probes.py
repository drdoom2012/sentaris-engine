"""Probe strategies for tests. They carry no market logic: they exercise the evaluation path and the strategy contract."""

from dataclasses import dataclass
from typing import Any, cast

from sentaris_engine.domain.evaluation import EvaluationContext, EvaluationFailure, NoSignal, Result, Signal, Signals
from sentaris_engine.domain.payload import Payload

PROBE_TIMEFRAME_MS = 300_000


@dataclass(frozen=True, slots=True)
class ScriptedProbe:
    """Returns the outcome it was given."""

    id: str
    version: str
    outcome: Result

    def evaluate(self, context: EvaluationContext) -> Result:
        return self.outcome


@dataclass(frozen=True, slots=True)
class BrokenProbe:
    """Returns `returns` as if it were a result, to show that a non-result is refused."""

    id: str
    version: str
    returns: object

    def evaluate(self, context: EvaluationContext) -> Result:
        return cast(Result, self.returns)


@dataclass(frozen=True, slots=True)
class RaisingProbe:
    """Raises `error` when evaluated."""

    id: str
    version: str
    error: Exception

    def evaluate(self, context: EvaluationContext) -> Result:
        raise self.error


@dataclass(frozen=True, slots=True)
class MutatingProbe:
    """Tries to replace the series of the snapshot it receives; returns no signal if nothing stopped it."""

    id: str
    version: str

    def evaluate(self, context: EvaluationContext) -> Result:
        cast(Any, context.snapshot).series = ()
        return NoSignal()


@dataclass(frozen=True, slots=True)
class LastCloseProbe:
    """Reports the last close of the 300_000 ms series, its count and `as_of`; `limit`, if given, must be a positive int."""

    id: str
    version: str

    def evaluate(self, context: EvaluationContext) -> Result:
        series = context.snapshot.series_for(PROBE_TIMEFRAME_MS)
        if series is None or not series.candles:
            return EvaluationFailure("series_missing")
        if "limit" in context.parameters:
            limit = context.parameters["limit"]
            if type(limit) is not int or limit <= 0:
                return EvaluationFailure("invalid_parameters")
        last = series.candles[-1]
        payload = Payload.of({"as_of": context.as_of, "close": last.close, "count": len(series.candles)})
        return Signals((Signal("probe.last_close", payload),))


@dataclass(frozen=True, slots=True)
class RecordingProbe:
    """Appends each context it receives to `seen` and returns `outcome`, to show whether and with what it ran."""

    id: str
    version: str
    outcome: Result
    seen: list[EvaluationContext]

    def evaluate(self, context: EvaluationContext) -> Result:
        self.seen.append(context)
        return self.outcome


@dataclass(frozen=True, slots=True)
class RecordingRaisingProbe:
    """Appends each context it receives to `seen`, then raises `error`."""

    id: str
    version: str
    error: Exception
    seen: list[EvaluationContext]

    def evaluate(self, context: EvaluationContext) -> Result:
        self.seen.append(context)
        raise self.error


class CountingIdentityProbe:
    """Counts how often its `id` and `version` are read; evaluates to no signal."""

    def __init__(self) -> None:
        self.id_reads = 0
        self.version_reads = 0

    @property
    def id(self) -> str:
        self.id_reads += 1
        return "counted"

    @property
    def version(self) -> str:
        self.version_reads += 1
        return "1"

    def evaluate(self, context: EvaluationContext) -> Result:
        return NoSignal()


class FailingStrError(Exception):
    """An exception whose `__str__` raises, to show that a report never reads an exception's text."""

    def __str__(self) -> str:
        raise RuntimeError("str failed")
