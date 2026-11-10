"""Strategy parameters: a flat immutable mapping from `str` to scalars (OD-13, ADR-0001).

A parameters object holds no null, sequence or mapping value. A value that is merely wrong for a particular strategy is
that strategy's evaluation failure; the engine never interprets parameters.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from decimal import Decimal
from typing import NoReturn, cast, final

from sentaris_engine.domain.payload import Payload

type ParameterValue = str | int | Decimal | bool


@final
class Parameters(Mapping[str, ParameterValue]):
    """Immutable mapping of scalar parameters; equal exactly when the canonical forms of their payloads are equal.

    Build it with `Parameters.of`. Keys iterate in code-point order.
    """

    __slots__ = ("_payload",)

    _payload: Payload

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("construct Parameters with Parameters.of")

    @staticmethod
    def of(source: dict[str, object] | Payload | Sequence[tuple[str, object]] = ()) -> Parameters:
        """Freeze `source` as parameters; it is accepted or rejected exactly as by `Payload.of`.

        Additionally raises `ValueError` for a null, sequence or mapping value.
        """
        payload = Payload.of(source)
        for key, value in payload.items():
            if value is None or type(value) is tuple or type(value) is Payload:
                raise ValueError(
                    f"parameter {key!r} must be a str, int, Decimal or bool, not a null, sequence or mapping"
                )
        parameters = object.__new__(Parameters)
        object.__setattr__(parameters, "_payload", payload)
        return parameters

    def __getitem__(self, key: str) -> ParameterValue:
        return cast(ParameterValue, self._payload[key])

    def __iter__(self) -> Iterator[str]:
        return iter(self._payload)

    def __len__(self) -> int:
        return len(self._payload)

    def __eq__(self, other: object) -> bool:
        if type(other) is not Parameters:
            return NotImplemented
        return self is other or self._payload == other._payload

    def __hash__(self) -> int:
        return hash(self._payload)

    def __repr__(self) -> str:
        return f"<Parameters {self._payload.canonical().decode('utf-8')}>"

    def __setattr__(self, name: str, value: object) -> NoReturn:
        raise AttributeError("Parameters are immutable")

    def __delattr__(self, name: str) -> NoReturn:
        raise AttributeError("Parameters are immutable")

    def __reduce__(self) -> tuple[Callable[[Payload], Parameters], tuple[Payload]]:
        return Parameters.of, (self._payload,)
