"""Signal payload: an immutable mapping with exactly one canonical byte form (OD-14; ADR-0001 is normative).

Construction and encoding are iterative, so no nesting depth raises `RecursionError` (ADR-0001: no depth bound).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from decimal import Decimal
from typing import Any, NoReturn, cast, final

MAX_SAFE_INT = 2**53 - 1


class PayloadError(ValueError):
    """A source is not a payload: a value, key or top-level shape outside ADR-0001."""


type PayloadValue = None | bool | int | str | Decimal | tuple[PayloadValue, ...] | Payload


@final
class Payload(Mapping[str, PayloadValue]):
    """Immutable mapping of payload values; equal exactly when the canonical forms are equal.

    Build it with `Payload.of`. Keys iterate in code-point order.
    """

    __slots__ = ("_canonical", "_index", "_items")

    _items: tuple[tuple[str, PayloadValue], ...]
    _index: dict[str, PayloadValue]
    _canonical: bytes | None

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("construct a Payload with Payload.of")

    @staticmethod
    def of(source: dict[str, object] | Payload | Sequence[tuple[str, object]] = ()) -> Payload:
        """Freeze `source` into a payload, or raise `PayloadError` if it is not one (ADR-0001).

        The top level is a `dict` with `str` keys, a `Payload`, or an exact `list` or `tuple` of exact `(str, value)`
        tuples. Containers are copied; nothing mutable stays reachable.
        """
        if type(source) is Payload:
            return source
        if type(source) is dict:
            return _freeze(source, list(source.items()))
        if type(source) is list or type(source) is tuple:
            entries: list[tuple[object, object]] = []
            for pair in cast(Sequence[object], source):
                if type(pair) is not tuple or len(pair) != 2 or type(pair[0]) is not str:
                    _reject(f"a top-level sequence must hold (str, value) pairs, got {type(pair).__name__}")
                entries.append((pair[0], pair[1]))
            return _freeze(source, entries)
        _reject(f"a payload source must be a dict, a Payload or a sequence of pairs, got {type(source).__name__}")

    def canonical(self) -> bytes:
        """The canonical form of ADR-0001, computed once and cached on this object."""
        if self._canonical is None:
            object.__setattr__(self, "_canonical", _encode(self))
        return cast(bytes, self._canonical)

    def __getitem__(self, key: str) -> PayloadValue:
        return self._index[key]

    def __iter__(self) -> Iterator[str]:
        return (key for key, _ in self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __eq__(self, other: object) -> bool:
        if type(other) is not Payload:
            return NotImplemented
        return self is other or self.canonical() == other.canonical()

    def __hash__(self) -> int:
        return hash(self.canonical())

    def __repr__(self) -> str:
        return f"<Payload {self.canonical().decode('utf-8')}>"

    def __setattr__(self, name: str, value: object) -> NoReturn:
        raise AttributeError("a Payload is immutable")

    def __delattr__(self, name: str) -> NoReturn:
        raise AttributeError("a Payload is immutable")

    def __reduce__(self) -> tuple[Callable[[bytes], Payload], tuple[bytes]]:
        # `from_canonical` is added with the decoder (SE-1, Task 2); until then reducing raises AttributeError.
        return cast(Any, Payload).from_canonical, (self.canonical(),)


def _reject(message: str) -> NoReturn:
    raise PayloadError(message)


def _new_payload(entries: list[tuple[str, PayloadValue]]) -> Payload:
    entries.sort(key=lambda entry: entry[0])
    payload = object.__new__(Payload)
    object.__setattr__(payload, "_items", tuple(entries))
    object.__setattr__(payload, "_index", dict(entries))
    object.__setattr__(payload, "_canonical", None)
    return payload


def _check_str(value: str, what: str) -> None:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        _reject(f"{what} contains a surrogate code point")


class _Frame:
    """One container being frozen: its source values, the frozen values so far, and, for a mapping, its keys."""

    __slots__ = ("frozen", "keys", "position", "source_id", "values")

    def __init__(self, source: object, keys: list[str] | None, values: list[object]) -> None:
        self.source_id = id(source)
        self.keys = keys
        self.values = values
        self.position = 0
        self.frozen: list[PayloadValue] = []


def _mapping_frame(source: object, entries: list[tuple[object, object]]) -> _Frame:
    keys: list[str] = []
    seen: set[str] = set()
    for key, _ in entries:
        if type(key) is not str:
            _reject(f"a mapping key must be a str, got {type(key).__name__}")
        _check_str(key, "a mapping key")
        if key in seen:
            _reject(f"duplicate mapping key {key!r}")
        seen.add(key)
        keys.append(key)
    return _Frame(source, keys, [value for _, value in entries])


def _freeze(source: object, entries: list[tuple[object, object]]) -> Payload:
    """Freeze a top-level mapping iteratively with an explicit stack of containers."""
    stack = [_mapping_frame(source, entries)]
    active = {stack[0].source_id}
    while True:
        frame = stack[-1]
        if frame.position == len(frame.values):
            stack.pop()
            active.discard(frame.source_id)
            done: PayloadValue
            if frame.keys is None:
                done = tuple(frame.frozen)
            else:
                done = _new_payload(list(zip(frame.keys, frame.frozen, strict=True)))
            if not stack:
                return cast(Payload, done)
            stack[-1].frozen.append(done)
            continue
        value = frame.values[frame.position]
        frame.position += 1
        kind = type(value)
        if value is None or kind is bool:
            frame.frozen.append(cast(bool | None, value))
        elif kind is int:
            if not -MAX_SAFE_INT <= cast(int, value) <= MAX_SAFE_INT:
                _reject(f"integer {value} is outside ±(2^53 - 1)")
            frame.frozen.append(cast(int, value))
        elif kind is str:
            _check_str(cast(str, value), "a string")
            frame.frozen.append(cast(str, value))
        elif kind is Decimal:
            if not cast(Decimal, value).is_finite():
                _reject(f"Decimal {value} is not finite")
            frame.frozen.append(cast(Decimal, value))
        elif kind is Payload:
            frame.frozen.append(cast(Payload, value))
        elif kind is list or kind is tuple or kind is dict:
            if id(value) in active:
                _reject("a container contains itself")
            if kind is dict:
                child = _mapping_frame(value, list(cast(dict[object, object], value).items()))
            else:
                child = _Frame(value, None, list(cast(Sequence[object], value)))
            stack.append(child)
            active.add(child.source_id)
        else:
            _reject(f"{kind.__name__} is not a payload value")


_STRING_ESCAPES: dict[int, str] = {code: f"\\u{code:04x}" for code in range(0x20)} | {
    0x08: "\\b",
    0x09: "\\t",
    0x0A: "\\n",
    0x0C: "\\f",
    0x0D: "\\r",
    0x22: '\\"',
    0x5C: "\\\\",
}


def _string_bytes(value: str) -> bytes:
    return ('"' + value.translate(_STRING_ESCAPES) + '"').encode("utf-8")


def _decimal_text(value: Decimal) -> str:
    """To-scientific-string of a finite `Decimal` from its sign, digits and exponent; reads no `decimal` context."""
    sign, digit_tuple, exponent = value.as_tuple()
    if type(exponent) is not int:
        _reject(f"Decimal {value} is not finite")
    digits = "".join(str(digit) for digit in digit_tuple)
    adjusted = exponent + len(digits) - 1
    if exponent <= 0 and adjusted >= -6:
        if exponent == 0:
            text = digits
        elif len(digits) > -exponent:
            text = digits[: len(digits) + exponent] + "." + digits[len(digits) + exponent :]
        else:
            text = "0." + "0" * (-exponent - len(digits)) + digits
    else:
        text = digits[0] + ("." + digits[1:] if len(digits) > 1 else "")
        text += "E" + ("+" if adjusted >= 0 else "-") + str(abs(adjusted))
    return "-" + text if sign else text


def _encode(payload: Payload) -> bytes:
    """Encode iteratively: the stack holds byte chunks to emit and values still to encode, last item first."""
    chunks: list[bytes] = []
    stack: list[object] = [payload]
    while stack:
        item = stack.pop()
        kind = type(item)
        if kind is bytes:
            chunks.append(cast(bytes, item))
        elif item is None:
            chunks.append(b"null")
        elif kind is bool:
            chunks.append(b"true" if item else b"false")
        elif kind is int:
            chunks.append(str(item).encode("ascii"))
        elif kind is str:
            chunks.append(_string_bytes(cast(str, item)))
        elif kind is Decimal:
            chunks.append(b'{"$decimal":"' + _decimal_text(cast(Decimal, item)).encode("ascii") + b'"}')
        elif kind is tuple:
            elements = cast(tuple[PayloadValue, ...], item)
            stack.append(b"]")
            for index in range(len(elements) - 1, -1, -1):
                stack.append(elements[index])
                if index:
                    stack.append(b",")
            stack.append(b"[")
        else:
            entries = cast(Payload, item)._items
            stack.append(b"}}")
            for index in range(len(entries) - 1, -1, -1):
                key, value = entries[index]
                stack.append(value)
                stack.append(_string_bytes(key) + b":")
                if index:
                    stack.append(b",")
            stack.append(b'{"$map":{')
    return b"".join(chunks)
