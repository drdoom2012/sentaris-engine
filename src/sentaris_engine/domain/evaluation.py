"""Stateless evaluation and the non-outcome report (DR-23, DR-26, DR-22, section 6.7; SE-4 spec 5.4)."""

from dataclasses import dataclass, field
from typing import final

from sentaris_engine.domain.context import EvaluationContext
from sentaris_engine.domain.errors import EvaluationTypeError
from sentaris_engine.domain.result import EvaluationFailure, NoSignal, Result, Signals
from sentaris_engine.domain.strategy import StatelessStrategy


@final
@dataclass(frozen=True, slots=True, eq=False)
class NotAnOutcome:
    """The type of a value a strategy returned that is not one of the three outcomes (U3, SE-4 spec 5.4 step 4).

    `returned_type` is a genuine class of any metaclass (R1); the value itself is not kept.
    """

    returned_type: type = field(repr=False)  # its metaclass may run strategy code (SE-4 spec 5.6)

    def __post_init__(self) -> None:
        if not type.__subclasscheck__(type, type(self.returned_type)):
            raise EvaluationTypeError("returned type is not a class")

    def __init_subclass__(cls, **kwargs: object) -> None:
        raise TypeError("NotAnOutcome cannot be subclassed")


def evaluate_stateless(strategy: StatelessStrategy, context: EvaluationContext) -> Result | NotAnOutcome:
    """Evaluate one stateless strategy once on `context` (DR-26, DR-22; SE-4 spec 5.4).

    An outcome is returned as the very object (DR-23); anything else is reported by its type only. Nothing is
    caught: every exception of the strategy propagates unchanged, and catching it is execution's (section 6.7).
    The strategy's identity is not read.
    """
    if not type.__subclasscheck__(StatelessStrategy, type(strategy)):
        raise EvaluationTypeError("strategy does not derive from StatelessStrategy")
    if type(context) is not EvaluationContext:
        raise EvaluationTypeError("context is not an exact EvaluationContext")
    value: object = strategy.evaluate(context)
    if type(value) is Signals:
        return value
    if type(value) is NoSignal:
        return value
    if type(value) is EvaluationFailure:
        return value
    return NotAnOutcome(type(value))
