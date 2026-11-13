"""Parameters: a flat immutable mapping of payload scalars (domain section 6.5; SE-3 U5)."""

from collections.abc import Iterator, Mapping
from decimal import Decimal
from typing import cast, final

from sentaris_engine.domain.errors import EvaluationTypeError
from sentaris_engine.domain.payload import FrozenMapping, PayloadError, is_payload_scalar

type _Scalar = bool | int | str | Decimal


@final
class Parameters(Mapping[str, _Scalar]):
    """Iterates in code-point key order (DR-10); equality and hash are by canonical form, never with a non-`Parameters`.

    The engine never reads the values (section 6.5); equality does not prejudge OD-17.
    """

    __slots__ = ("_mapping",)
    _mapping: FrozenMapping

    def __init__(self, source: object) -> None:
        if hasattr(self, "_mapping"):
            raise TypeError("Parameters is already initialised")
        if type(source) is not dict and type(source) is not list and type(source) is not tuple:
            raise EvaluationTypeError("parameters source is not an exact dict, or list or tuple of pairs")
        try:
            mapping = FrozenMapping(source)
        except PayloadError as exc:
            raise EvaluationTypeError("parameters are not a valid flat mapping (section 6.5)") from exc
        for value in mapping.values():
            if not is_payload_scalar(value):
                raise EvaluationTypeError("parameter value is not a scalar (section 6.5)")
        object.__setattr__(self, "_mapping", mapping)

    def __init_subclass__(cls, **kwargs: object) -> None:
        raise TypeError("Parameters cannot be subclassed")

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("Parameters is immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("Parameters is immutable")

    def __getitem__(self, key: str) -> _Scalar:
        return cast(_Scalar, self._mapping[key])

    def __iter__(self) -> Iterator[str]:
        return iter(self._mapping)

    def __len__(self) -> int:
        return len(self._mapping)

    def __eq__(self, other: object) -> bool:
        if type(other) is not Parameters:
            return NotImplemented
        return self._mapping.canonical_bytes() == other._mapping.canonical_bytes()

    def __hash__(self) -> int:
        return hash(self._mapping.canonical_bytes())

    def __repr__(self) -> str:
        return "Parameters(" + self._mapping.canonical_bytes().decode("utf-8") + ")"
