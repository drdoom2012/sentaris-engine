"""Forming a declaration from a strategy and the non-declaration report (section 6.9, section 6.8; SE-7a spec 5.5)."""

from dataclasses import dataclass, field
from typing import final

from sentaris_engine.domain.declaration import Declaration
from sentaris_engine.domain.errors import EvaluationTypeError
from sentaris_engine.domain.parameters import Parameters
from sentaris_engine.domain.result import EvaluationFailure
from sentaris_engine.domain.strategy import StatefulStrategy, StatelessStrategy


@final
@dataclass(frozen=True, slots=True, eq=False)
class NotADeclaration:
    """The type of a value `declare` returned that is neither a declaration nor a failure (SE-7a spec 5.5 step 4).

    `returned_type` is a genuine class of any metaclass; the value itself is not kept.
    """

    returned_type: type = field(repr=False)  # its metaclass may run strategy code (SE-4 spec 5.6)

    def __post_init__(self) -> None:
        if not type.__subclasscheck__(type, type(self.returned_type)):
            raise EvaluationTypeError("returned type is not a class")

    def __init_subclass__(cls, **kwargs: object) -> None:
        raise TypeError("NotADeclaration cannot be subclassed")


def declare_inputs(
    strategy: StatelessStrategy | StatefulStrategy, parameters: Parameters
) -> Declaration | EvaluationFailure | NotADeclaration:
    """Ask one strategy what it needs for `parameters` (section 6.9; SE-7a spec 5.5).

    A declaration or a failure is returned as the very object; anything else is reported by its type only. Nothing
    is caught: every exception of `declare` propagates unchanged, and what a pair reports for it is decided where
    this is called (OD-13, OD-3). The strategy's identity is not read.
    """
    strategy_type = type(strategy)
    if not (
        type.__subclasscheck__(StatelessStrategy, strategy_type)
        or type.__subclasscheck__(StatefulStrategy, strategy_type)
    ):
        raise EvaluationTypeError("strategy does not derive from StatelessStrategy or StatefulStrategy")
    if type(parameters) is not Parameters:
        raise EvaluationTypeError("parameters is not an exact Parameters")
    value: object = strategy.declare(parameters)
    if type(value) is Declaration:
        return value
    if type(value) is EvaluationFailure:
        return value
    return NotADeclaration(type(value))
