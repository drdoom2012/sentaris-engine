"""Payload values: construction, the immutable mapping, its canonical form and the strict decoder (domain 6.3, A).

Every operation over the payload structure uses an explicit work stack, never recursion (SE-2 spec 5.3, U1).
"""

from collections.abc import Iterator, Mapping, Sequence
from decimal import Decimal, InvalidOperation, localcontext
from typing import Final, cast, final

type PayloadValue = None | bool | int | str | Decimal | tuple[PayloadValue, ...] | FrozenMapping

MAX_INT: Final = 2**53 - 1


class PayloadError(ValueError):
    """A value or source shape outside A.1, or bytes that are not a canonical form (A.2).

    The message content is free (SE-2 spec 5.1); a message is never reported (domain section 6.7).
    """


def _has_surrogate(text: str) -> bool:
    return any("\ud800" <= ch <= "\udfff" for ch in text)


def is_payload_scalar(value: object) -> bool:
    """True exactly for the four scalar kinds of A.1, matched by exact type; never raises."""
    if type(value) is bool:
        return True
    if type(value) is int:
        return -MAX_INT <= value <= MAX_INT
    if type(value) is str:
        return not _has_surrogate(value)
    if type(value) is Decimal:
        return value.is_finite()
    return False


def _check_key(key: object) -> str:
    if type(key) is not str or _has_surrogate(key):
        raise PayloadError("mapping key is not a str without surrogate code points (A.1)")
    return key


@final
class FrozenMapping(Mapping[str, PayloadValue]):
    """The engine's immutable mapping of A.1; iteration is in code-point key order (DR-10)."""

    __slots__ = ("_bytes", "_items")
    _items: dict[str, PayloadValue]
    _bytes: bytes | None

    def __init__(self, source: object) -> None:
        if hasattr(self, "_items"):
            raise TypeError("FrozenMapping is already initialised")
        if type(source) is FrozenMapping:
            items = source._items
            cached = source._bytes
        else:
            items = _freeze(_root_frame(source))
            cached = None
        object.__setattr__(self, "_items", items)
        object.__setattr__(self, "_bytes", cached)

    @classmethod
    def _from_frozen_items(cls, items: dict[str, PayloadValue]) -> "FrozenMapping":
        """Wrap frozen, valid items whose keys are already in code-point order; no check, no sort (plan M5)."""
        mapping = object.__new__(cls)
        object.__setattr__(mapping, "_items", items)
        object.__setattr__(mapping, "_bytes", None)
        return mapping

    def __init_subclass__(cls, **kwargs: object) -> None:
        raise TypeError("FrozenMapping cannot be subclassed (A.1)")

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("FrozenMapping is immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("FrozenMapping is immutable")

    def canonical_bytes(self) -> bytes:
        """The A.2 canonical form; cached on this mapping only, never on nested ones (SE-2 spec 5.3)."""
        cached = self._bytes
        if cached is None:
            cached = _encode(self)
            object.__setattr__(self, "_bytes", cached)
        return cached

    def __getitem__(self, key: str) -> PayloadValue:
        return self._items[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __eq__(self, other: object) -> bool:
        """Equal exactly when the canonical forms are equal (domain section 6.3, A.1 "Equality")."""
        if type(other) is not FrozenMapping:
            return NotImplemented
        return other is self or self.canonical_bytes() == other.canonical_bytes()

    def __hash__(self) -> int:
        return hash(self.canonical_bytes())

    def __repr__(self) -> str:
        return "FrozenMapping(" + self.canonical_bytes().decode("utf-8") + ")"


class _Frame:
    """One source container on the work stack: its children and the frozen values produced so far."""

    __slots__ = ("children", "frozen", "keys", "source_id")

    def __init__(self, source_id: int, keys: list[str] | None, children: Sequence[object]) -> None:
        self.source_id = source_id
        self.keys = keys  # None for a sequence; sorted keys for a mapping
        self.children = children
        self.frozen: list[PayloadValue] = []


def _enter(container: list[object] | tuple[object, ...] | dict[object, object]) -> _Frame:
    if type(container) is dict:
        keys = [_check_key(key) for key in container]
        keys.sort()
        return _Frame(id(container), keys, [container[key] for key in keys])
    return _Frame(id(container), None, cast(Sequence[object], container))


def _root_frame(source: object) -> _Frame:
    """The top-level frame for a source shape of SE-2 spec 5.1; any other shape is rejected."""
    if type(source) is dict:
        return _enter(source)
    if type(source) is list or type(source) is tuple:
        values: dict[str, object] = {}
        for pair in source:
            if type(pair) is not tuple or len(pair) != 2:
                raise PayloadError("pair source element is not a 2-tuple")
            key = _check_key(pair[0])
            if key in values:
                raise PayloadError("duplicate key (A.1)")
            values[key] = pair[1]
        keys = sorted(values)
        return _Frame(id(source), keys, [values[key] for key in keys])
    raise PayloadError("source is not a dict, a FrozenMapping or a list or tuple of pairs")


def _freeze(root: _Frame) -> dict[str, PayloadValue]:
    """Validate and freeze depth-first from `root`; return the root's frozen items in key order.

    A child frame is pushed only when the walk enters it, so `in_progress` holds exactly the ancestors of the
    current position: reaching one again is a cycle; a `finished` container is shared and reused (SE-2 spec 5.1).
    """
    in_progress = {root.source_id}
    finished: dict[int, PayloadValue] = {}
    stack = [root]
    while True:
        frame = stack[-1]
        position = len(frame.frozen)
        if position < len(frame.children):
            child = frame.children[position]
            if child is None or type(child) is FrozenMapping:
                frame.frozen.append(child)
            elif is_payload_scalar(child):
                frame.frozen.append(cast(PayloadValue, child))
            elif type(child) is list or type(child) is tuple or type(child) is dict:
                child_id = id(child)
                if child_id in in_progress:
                    raise PayloadError("cyclic container (A.1)")
                if child_id in finished:
                    frame.frozen.append(finished[child_id])
                else:
                    in_progress.add(child_id)
                    stack.append(_enter(child))
            else:
                raise PayloadError("value is not of a kind accepted by A.1")
            continue
        stack.pop()
        in_progress.remove(frame.source_id)
        if frame.keys is None:
            value: PayloadValue = tuple(frame.frozen)
        else:
            items = dict(zip(frame.keys, frame.frozen, strict=True))
            if not stack:
                return items
            value = FrozenMapping._from_frozen_items(items)
        finished[frame.source_id] = value
        stack[-1].frozen.append(value)


# A.2 string row: exactly these code points are escaped.
_STRING_ESCAPES: Final[dict[int, str]] = {
    **{code: "\\u00" + "0123456789abcdef"[code >> 4] + "0123456789abcdef"[code & 0xF] for code in range(0x20)},
    0x08: "\\b",
    0x09: "\\t",
    0x0A: "\\n",
    0x0C: "\\f",
    0x0D: "\\r",
    ord('"'): '\\"',
    ord("\\"): "\\\\",
}

_DIGITS: Final = "0123456789"


def _string_text(text: str) -> str:
    """The A.2 encoding of a `str`, quotes included."""
    return '"' + text.translate(_STRING_ESCAPES) + '"'


def _decimal_text(d: Decimal) -> str:
    """The A.2 `$decimal` text, from `as_tuple()` alone (SE-2 spec 5.4); never reads the `decimal` context."""
    sign, digits, exponent = d.as_tuple()
    if type(exponent) is not int:
        raise TypeError("not a finite Decimal; construction admits only finite ones (A.1)")
    coefficient = "".join([_DIGITS[digit] for digit in digits])
    length = len(coefficient)
    adjusted = exponent + length - 1
    if exponent == 0:
        text = coefficient
    elif exponent < 0 and adjusted >= -6:
        point = length + exponent
        if point <= 0:
            text = "0." + "0" * -point + coefficient
        else:
            text = coefficient[:point] + "." + coefficient[point:]
    else:
        fraction = "." + coefficient[1:] if length > 1 else ""
        text = coefficient[0] + fraction + "E" + ("+" if adjusted >= 0 else "-") + str(abs(adjusted))
    return "-" + text if sign else text


def _scalar_text(value: PayloadValue) -> str:
    """The A.2 encoding of `None` or a scalar; `bool` is tested before `int` is ever considered (exact types)."""
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if type(value) is int:
        return str(value)
    if type(value) is str:
        return _string_text(value)
    return '{"$decimal":"' + _decimal_text(cast(Decimal, value)) + '"}'


def _encode(root: FrozenMapping) -> bytes:
    """One pass over `root` with an explicit stack (SE-2 spec 5.3); nested mappings are not cached.

    The stack holds finished text (a `str`) or a container still to be expanded (a `tuple` or `FrozenMapping`);
    a container is expanded into its text pieces in reverse, so the next piece is always on top.
    """
    pieces: list[str] = []
    stack: list[str | tuple[PayloadValue, ...] | FrozenMapping] = [root]
    while stack:
        item = stack.pop()
        if type(item) is str:
            pieces.append(item)
            continue
        expanded: list[str | tuple[PayloadValue, ...] | FrozenMapping] = []
        if type(item) is FrozenMapping:
            expanded.append('{"$map":{')
            for position, (key, value) in enumerate(item._items.items()):
                prefix = ("," if position else "") + _string_text(key) + ":"
                if type(value) is tuple or type(value) is FrozenMapping:
                    expanded.extend((prefix, value))
                else:
                    expanded.append(prefix + _scalar_text(value))
            expanded.append("}}")
        else:
            expanded.append("[")
            for position, value in enumerate(cast(tuple[PayloadValue, ...], item)):
                if position:
                    expanded.append(",")
                if type(value) is tuple or type(value) is FrozenMapping:
                    expanded.append(value)
                else:
                    expanded.append(_scalar_text(value))
            expanded.append("]")
        expanded.reverse()
        stack.extend(expanded)
    return "".join(pieces).encode("utf-8")


def _decimal_from_text(text: str) -> Decimal:
    """The one place the decoder builds a `Decimal` from text (SE-2 spec 5.5, N16)."""
    return Decimal(text)


_MAP_OPEN: Final = '{"$map":{'
_DECIMAL_OPEN: Final = '{"$decimal":"'
_HEX: Final = "0123456789abcdef"
# A.2 string row: the short escapes and the character each one stands for.
_SHORT_ESCAPES: Final[dict[str, str]] = {'"': '"', "\\": "\\", "b": "\b", "t": "\t", "n": "\n", "f": "\f", "r": "\r"}
_SHORT_ESCAPED_CODES: Final = frozenset({0x08, 0x09, 0x0A, 0x0C, 0x0D})
_MAX_INT_DIGITS: Final = 16  # MAX_INT has 16 digits (SE-2 spec 5.6)


class _Open:
    """One container on the decoder's work stack: its keys (None for a sequence) and its finished values."""

    __slots__ = ("keys", "values")

    def __init__(self, keys: list[str] | None) -> None:
        self.keys = keys
        self.values: list[PayloadValue] = []


def _string_at(text: str, pos: int) -> tuple[str, int]:
    """The A.2 string starting at `pos` and the position after it; only canonical escapes are accepted."""
    end = len(text)
    if not text.startswith('"', pos):
        raise PayloadError("expected a string (A.2)")
    pos += 1
    parts: list[str] = []
    while True:
        if pos >= end:
            raise PayloadError("unterminated string (A.2)")
        ch = text[pos]
        if ch == '"':
            return "".join(parts), pos + 1
        if ch == "\\":
            if pos + 1 >= end:
                raise PayloadError("unterminated escape (A.2)")
            short = _SHORT_ESCAPES.get(text[pos + 1])
            if short is not None:
                parts.append(short)
                pos += 2
                continue
            if pos + 6 <= end and text.startswith("u00", pos + 1) and text[pos + 4] in "01" and text[pos + 5] in _HEX:
                code = int(text[pos + 4 : pos + 6], 16)
                if code not in _SHORT_ESCAPED_CODES:
                    parts.append(chr(code))
                    pos += 6
                    continue
            raise PayloadError("non-canonical escape (A.2)")
        if ch < " ":
            raise PayloadError("unescaped control character (A.2)")
        parts.append(ch)
        pos += 1


def _integer_at(text: str, pos: int) -> tuple[int, int]:
    """The integer starting at `pos`: shape and length checked before `int()`, range after (SE-2 spec 5.6)."""
    end = len(text)
    start = pos
    if text.startswith("-", pos):
        pos += 1
    digits_start = pos
    while pos < end and pos - digits_start <= _MAX_INT_DIGITS and text[pos] in _DIGITS:
        pos += 1
    digits = text[digits_start:pos]
    if not digits or len(digits) > _MAX_INT_DIGITS:
        raise PayloadError("integer token has no digits or too many (A.1)")
    if digits[0] == "0" and (len(digits) > 1 or digits_start != start):
        raise PayloadError("integer with a leading zero or negative zero (A.2)")
    value = int(text[start:pos])
    if not -MAX_INT <= value <= MAX_INT:
        raise PayloadError("integer outside the A.1 range")
    return value, pos


def _decimal_at(text: str, pos: int) -> tuple[Decimal, int]:
    """The `$decimal` text starting at `pos` (after its opening) and the position after the closing `"}`."""
    close = text.find('"', pos)
    if close < 0 or not text.startswith('"}', close):
        raise PayloadError("malformed $decimal (A.2)")
    with localcontext():  # the caller's context flags stay untouched (SE-2 spec 5.5)
        try:
            value = _decimal_from_text(text[pos:close])
        except InvalidOperation as exc:
            raise PayloadError("malformed $decimal text (A.2)") from exc
    if not value.is_finite():
        raise PayloadError("$decimal is not finite (A.1)")
    return value, close + 2


def _scalar_at(text: str, pos: int) -> tuple[PayloadValue, int]:
    """The `null`, scalar or `$decimal` token starting at `pos` and the position after it."""
    if text.startswith(_DECIMAL_OPEN, pos):
        return _decimal_at(text, pos + len(_DECIMAL_OPEN))
    if text.startswith('"', pos):
        return _string_at(text, pos)
    if text.startswith("true", pos):
        return True, pos + 4
    if text.startswith("false", pos):
        return False, pos + 5
    if text.startswith("null", pos):
        return None, pos + 4
    if text.startswith("-", pos) or (pos < len(text) and text[pos] in _DIGITS):
        return _integer_at(text, pos)
    raise PayloadError("unexpected token (A.2)")


def _sorted_items(keys: list[str], values: list[PayloadValue]) -> dict[str, PayloadValue]:
    """Items in code-point key order, as `_from_frozen_items` requires (plan M5); a repeated key is rejected."""
    order = sorted(range(len(keys)), key=keys.__getitem__)
    items = {keys[index]: values[index] for index in order}
    if len(items) != len(keys):
        raise PayloadError("duplicate key (A.1)")
    return items


def _parse(text: str) -> FrozenMapping:
    """Candidate payload of `text`, built bottom-up with an explicit stack (SE-2 spec 5.3, 5.5)."""
    if not text.startswith(_MAP_OPEN):
        raise PayloadError("top level is not a mapping (A.2)")
    pos = len(_MAP_OPEN)
    stack = [_Open([])]
    while True:
        top = stack[-1]
        closing = "]" if top.keys is None else "}}"
        if text.startswith(closing, pos):
            pos += len(closing)
            stack.pop()
            if top.keys is None:
                value: PayloadValue = tuple(top.values)
            else:
                mapping = FrozenMapping._from_frozen_items(_sorted_items(top.keys, top.values))
                if not stack:
                    if pos != len(text):
                        raise PayloadError("data after the top-level mapping (A.2)")
                    return mapping
                value = mapping
            stack[-1].values.append(value)
            continue
        if top.values:
            if not text.startswith(",", pos):
                raise PayloadError("expected a separator or the end of a container (A.2)")
            pos += 1
        if top.keys is not None:
            key, pos = _string_at(text, pos)
            if not text.startswith(":", pos):
                raise PayloadError("expected ':' after a key (A.2)")
            pos += 1
            top.keys.append(key)
        if text.startswith(_MAP_OPEN, pos):
            stack.append(_Open([]))
            pos += len(_MAP_OPEN)
        elif text.startswith("[", pos):
            stack.append(_Open(None))
            pos += 1
        else:
            scalar, pos = _scalar_at(text, pos)
            top.values.append(scalar)


def decode_payload(data: object) -> FrozenMapping:
    """The payload whose canonical form is exactly `data`; anything else is rejected (A.2 "Required properties").

    The parser may be lenient where the final re-encoding check catches it, never where it would build a value
    outside A.1 (SE-2 spec 5.5).
    """
    if type(data) is not bytes:
        raise PayloadError("decoder input is not bytes")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PayloadError("input is not valid UTF-8 (A.2)") from exc
    result = _parse(text)
    if result.canonical_bytes() != data:
        raise PayloadError("input is not the canonical form of its payload (A.2)")
    return result
