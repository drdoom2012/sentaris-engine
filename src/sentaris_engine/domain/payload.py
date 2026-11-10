"""Signal payload: an immutable mapping with exactly one canonical byte form (OD-14; ADR-0001 is normative).

Construction, encoding and decoding are iterative, so no depth raises `RecursionError` (ADR-0001: no depth bound).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any, NoReturn, cast, final

MAX_SAFE_INT = 2**53 - 1


class PayloadError(ValueError):
    """A source is not a payload: a value, key or top-level shape outside ADR-0001."""


type PayloadValue = None | bool | int | str | Decimal | tuple[PayloadValue, ...] | Payload


@final
class Payload(Mapping[str, PayloadValue]):
    """Immutable mapping of payload values; equal exactly when the canonical forms are equal.

    Build it with `Payload.of`. Keys iterate in code-point order. A lookup is a binary search over the sorted key
    tuple, so no mutable lookup structure is reachable from a payload.
    """

    __slots__ = ("_canonical", "_items", "_keys")

    _items: tuple[tuple[str, PayloadValue], ...]
    _keys: tuple[str, ...]
    _canonical: bytes | None

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("construct a Payload with Payload.of")

    @staticmethod
    def of(source: dict[str, Any] | Payload | Sequence[tuple[str, Any]] = ()) -> Payload:
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

    @classmethod
    def from_canonical(cls, data: bytes) -> Payload:
        """The payload whose canonical form is exactly `data`; anything else raises `PayloadError` (ADR-0001)."""
        if type(data) is not bytes:
            _reject(f"canonical form must be bytes, got {type(data).__name__}")
        try:
            payload = _decode(data.decode("utf-8"))
        except PayloadError:
            raise
        except (InvalidOperation, ValueError, UnicodeDecodeError, IndexError) as error:
            raise PayloadError(f"not a canonical form: {error}") from error
        if payload.canonical() != data:
            _reject("not the canonical form of the payload it encodes")
        return payload

    def canonical(self) -> bytes:
        """The canonical form of ADR-0001, computed once and cached on this object."""
        if self._canonical is None:
            object.__setattr__(self, "_canonical", _encode(self))
        return cast(bytes, self._canonical)

    def __getitem__(self, key: str) -> PayloadValue:
        if isinstance(key, str):
            keys = self._keys
            low, high = 0, len(keys)
            while low < high:  # binary search for the first key not below `key`; the keys are sorted, never mutable
                middle = (low + high) // 2
                if keys[middle] < key:
                    low = middle + 1
                else:
                    high = middle
            if low < len(keys) and keys[low] == key:
                return self._items[low][1]
        raise KeyError(key)

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
        return Payload.from_canonical, (self.canonical(),)


def _reject(message: str) -> NoReturn:
    raise PayloadError(message)


def _new_payload(entries: list[tuple[str, PayloadValue]]) -> Payload:
    entries.sort(key=lambda entry: entry[0])
    payload = object.__new__(Payload)
    object.__setattr__(payload, "_items", tuple(entries))
    object.__setattr__(payload, "_keys", tuple(key for key, _ in entries))
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


_DIGITS = frozenset("0123456789")
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")
_SIMPLE_ESCAPES = {'"': '"', "\\": "\\", "b": "\b", "t": "\t", "n": "\n", "f": "\f", "r": "\r"}
_MAX_INT_DIGITS = 16


class _Reader:
    """A position in decoded text, with the readers for the shapes the encoder produces and nothing else."""

    __slots__ = ("pos", "text")

    def __init__(self, text: str) -> None:
        self.text = text
        self.pos = 0

    def take(self, literal: str) -> bool:
        if self.text.startswith(literal, self.pos):
            self.pos += len(literal)
            return True
        return False

    def expect(self, literal: str) -> None:
        if not self.take(literal):
            _reject(f"expected {literal!r} at offset {self.pos}")

    def string(self) -> str:
        """A string body after its opening quote, through the closing quote."""
        text = self.text
        parts: list[str] = []
        start = self.pos
        while True:
            char = text[self.pos]
            if char == '"':
                parts.append(text[start : self.pos])
                self.pos += 1
                return "".join(parts)
            if char != "\\":
                self.pos += 1
                continue
            parts.append(text[start : self.pos])
            escape = text[self.pos + 1]
            if escape in _SIMPLE_ESCAPES:
                parts.append(_SIMPLE_ESCAPES[escape])
                self.pos += 2
            elif escape == "u":
                hex_digits = text[self.pos + 2 : self.pos + 6]
                if len(hex_digits) != 4 or not all(digit in _HEX_DIGITS for digit in hex_digits):
                    _reject(f"invalid \\u escape at offset {self.pos}")
                parts.append(chr(int(hex_digits, 16)))
                self.pos += 6
            else:
                _reject(f"invalid escape at offset {self.pos}")
            start = self.pos

    def key(self) -> str:
        """A mapping entry's key and the colon after it."""
        self.expect('"')
        key = self.string()
        self.expect(":")
        return key

    def scalar(self) -> PayloadValue:
        if self.take("null"):
            return None
        if self.take("true"):
            return True
        if self.take("false"):
            return False
        if self.take('"'):
            return self.string()
        if self.take('{"$decimal":"'):
            end = self.text.find('"', self.pos)
            if end < 0:
                _reject("unterminated Decimal text")
            value = Decimal(self.text[self.pos : end])
            if not value.is_finite():
                _reject(f"Decimal {value} is not finite")
            self.pos = end
            self.expect('"}')
            return value
        start = self.pos
        self.take("-")
        digits_start = self.pos
        while self.pos < len(self.text) and self.text[self.pos] in _DIGITS:
            self.pos += 1
            if self.pos - digits_start > _MAX_INT_DIGITS:
                _reject(f"integer at offset {start} has more than {_MAX_INT_DIGITS} digits")
        if self.pos == digits_start:
            _reject(f"no payload value at offset {start}")
        return int(self.text[start : self.pos])


class _Open:
    """A container being decoded: its keys (a mapping) or `None` (a sequence), and its values so far."""

    __slots__ = ("keys", "values")

    def __init__(self, keys: list[str] | None) -> None:
        self.keys = keys
        self.values: list[PayloadValue] = []


def _close(frame: _Open) -> PayloadValue:
    if frame.keys is None:
        return tuple(frame.values)
    return Payload.of(list(zip(frame.keys, frame.values, strict=True)))


def _decode(text: str) -> Payload:
    """Decode iteratively with an explicit stack of open containers; whitespace and every other shape is rejected."""
    reader = _Reader(text)
    stack: list[_Open] = []
    while True:
        done: PayloadValue
        if reader.take("["):
            stack.append(_Open(None))
            if not reader.take("]"):
                continue
            done = _close(stack.pop())
        elif reader.take('{"$map":{'):
            stack.append(_Open([]))
            if not reader.take("}}"):
                cast(list[str], stack[-1].keys).append(reader.key())
                continue
            done = _close(stack.pop())
        else:
            done = reader.scalar()
        while stack:
            frame = stack[-1]
            frame.values.append(done)
            if reader.take(","):
                if frame.keys is not None:
                    frame.keys.append(reader.key())
                break
            reader.expect("]" if frame.keys is None else "}}")
            done = _close(stack.pop())
        else:
            if reader.pos != len(text):
                _reject(f"unexpected data at offset {reader.pos}")
            if type(done) is not Payload:
                _reject("the top level of a canonical form is a mapping")
            return done
