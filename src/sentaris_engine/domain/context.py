"""The evaluation context of one (strategy, instrument) pair (domain sections 3, 6.7; DR-26; SE-3 spec 5.8).

It carries no state, no instrument key (section 6.8) and no mode flag (DR-12).
"""

from dataclasses import dataclass
from typing import final

from sentaris_engine.domain.errors import EvaluationTypeError
from sentaris_engine.domain.parameters import Parameters
from sentaris_engine.domain.snapshot import Snapshot
from sentaris_engine.domain.timing import check_instant


@final
@dataclass(frozen=True, slots=True, eq=False)
class EvaluationContext:
    """Equality and hash are by identity (SE-3 spec 5.7)."""

    snapshot: Snapshot
    parameters: Parameters
    as_of: int

    def __post_init__(self) -> None:
        if type(self.snapshot) is not Snapshot:
            raise EvaluationTypeError("snapshot is not an exact Snapshot")
        if type(self.parameters) is not Parameters:
            raise EvaluationTypeError("parameters is not an exact Parameters")
        if check_instant(self.as_of) != self.snapshot.as_of:
            raise EvaluationTypeError("as_of differs from the snapshot's as_of (SE-3 spec 5.8)")

    def __init_subclass__(cls, **kwargs: object) -> None:
        raise TypeError("EvaluationContext cannot be subclassed")
