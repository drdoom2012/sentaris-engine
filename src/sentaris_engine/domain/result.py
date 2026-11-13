"""The three outcomes of an evaluation (domain section 6.2, DR-14; SE-3 spec 5.5)."""

from dataclasses import dataclass
from typing import final

from sentaris_engine.domain.errors import EvaluationTypeError
from sentaris_engine.domain.payload import has_surrogate
from sentaris_engine.domain.signal import Signal


@final
@dataclass(frozen=True, slots=True)
class Signals:
    """One or more signals, kept in the given order and never sorted; duplicates are kept (U7, OD-18)."""

    signals: tuple[Signal, ...]

    def __post_init__(self) -> None:
        if type(self.signals) is not tuple:
            raise EvaluationTypeError("signals is not an exact tuple")
        if not self.signals:
            raise EvaluationTypeError("signals outcome needs at least one signal (DR-14)")
        for signal in self.signals:
            if type(signal) is not Signal:
                raise EvaluationTypeError("signals holds an element that is not a Signal")

    def __init_subclass__(cls, **kwargs: object) -> None:
        raise TypeError("Signals cannot be subclassed")


@final
@dataclass(frozen=True, slots=True)
class NoSignal:
    """No signal; all instances are equal."""

    def __init_subclass__(cls, **kwargs: object) -> None:
        raise TypeError("NoSignal cannot be subclassed")


@final
@dataclass(frozen=True, slots=True)
class EvaluationFailure:
    """A failure with a machine-readable code; the taxonomy is open (OD-3) and there is no evidence field."""

    code: str

    def __post_init__(self) -> None:
        if type(self.code) is not str or not self.code or has_surrogate(self.code):
            raise EvaluationTypeError("failure code is not a non-empty exact str without surrogates (U3)")

    def __init_subclass__(cls, **kwargs: object) -> None:
        raise TypeError("EvaluationFailure cannot be subclassed")


type Result = Signals | NoSignal | EvaluationFailure
