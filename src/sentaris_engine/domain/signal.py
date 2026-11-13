"""Signal: a kind and a payload (domain section 6.3; SE-3 spec 5.4)."""

from dataclasses import dataclass
from typing import final

from sentaris_engine.domain.errors import EvaluationTypeError
from sentaris_engine.domain.payload import FrozenMapping, has_surrogate


@final
@dataclass(frozen=True, slots=True)
class Signal:
    """Equality is by kind and canonical payload form (SE-2); the hash agrees. The kind taxonomy is open (OD-3)."""

    kind: str
    payload: FrozenMapping

    def __post_init__(self) -> None:
        if type(self.kind) is not str or not self.kind or has_surrogate(self.kind):
            raise EvaluationTypeError("signal kind is not a non-empty exact str without surrogates (U3)")
        if type(self.payload) is not FrozenMapping:
            raise EvaluationTypeError("signal payload is not exactly a FrozenMapping")

    def __init_subclass__(cls, **kwargs: object) -> None:
        raise TypeError("Signal cannot be subclassed")
