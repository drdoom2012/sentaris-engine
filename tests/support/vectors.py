"""Payload test data shared by in-process and cross-process tests (ADR-0001, "Canonical form of a payload").

Every entry holds a builder, not a value, so that each process builds its own values under its own `decimal` context.
This module imports nothing from `tests.*`: a child process started for a cross-process test cannot import `tests`.
"""

import random
from collections import OrderedDict, defaultdict, namedtuple
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum, IntEnum
from types import MappingProxyType
from typing import Any


class _Color(IntEnum):
    RED = 1


class _Side(str, Enum):  # noqa: UP042 -- ADR-0001 names the (str, Enum) mixin, not StrEnum
    BUY = "buy"


class _Str(str):
    pass


class _Int(int):
    pass


class _Decimal(Decimal):
    pass


class _List(list[Any]):
    pass


class _Dict(dict[str, Any]):
    pass


_Pair = namedtuple("_Pair", ["key", "value"])


@dataclass(frozen=True)
class _Point:
    x: int


def _generator() -> Iterator[int]:
    yield 1


def _generator_of_pairs() -> Iterator[tuple[str, int]]:
    yield ("a", 1)


def _cyclic_list() -> list[Any]:
    cycle: list[Any] = []
    cycle.append(cycle)
    return cycle


def _cyclic_dict() -> dict[str, Any]:
    cycle: dict[str, Any] = {}
    cycle["a"] = cycle
    return cycle


# (id, builder of the top-level source, exact canonical bytes): the ADR-0001 test vectors.
VECTORS: list[tuple[str, Callable[[], Any], bytes]] = [
    ("empty", dict, b'{"$map":{}}'),
    ("bool-and-int", lambda: {"b": 1, "a": True}, b'{"$map":{"a":true,"b":1}}'),
    (
        "decimals",
        lambda: {"p": Decimal("64210.50"), "q": Decimal("-0"), "r": Decimal("1E+2"), "s": Decimal("0.0000001")},
        b'{"$map":{"p":{"$decimal":"64210.50"},"q":{"$decimal":"-0"},"r":{"$decimal":"1E+2"},"s":{"$decimal":"1E-7"}}}',
    ),
    (
        "null-and-sequences",
        lambda: {"x": None, "y": [], "z": ["1", 1, None, {}]},
        b'{"$map":{"x":null,"y":[],"z":["1",1,null,{"$map":{}}]}}',
    ),
    (
        "string-escapes",
        lambda: {"$map": "k", "é": 'a"b\\c\n\x01'},
        '{"$map":{"$map":"k","é":"a\\"b\\\\c\\n\\u0001"}}'.encode(),
    ),
    ("key-order", lambda: {"Z": 0, "a": -5, "ab": 2, "aa": 3}, b'{"$map":{"Z":0,"a":-5,"aa":3,"ab":2}}'),
    (
        "integer-range",
        lambda: {"max": 9007199254740991, "min": -9007199254740991},
        b'{"$map":{"max":9007199254740991,"min":-9007199254740991}}',
    ),
    (
        "decimal-exponent-and-tuple",
        lambda: {"d": Decimal("-1.50E-12"), "t": (True, False)},
        b'{"$map":{"d":{"$decimal":"-1.50E-12"},"t":[true,false]}}',
    ),
]

# Top-level sources that construction must reject with `PayloadError`. Some are valid as nested values (a nested
# `["ab"]` is a sequence), so they are not in `REJECTED_VALUES`.
REJECTED: list[tuple[str, Callable[[], Any]]] = [
    # ADR-0001, "Rejected at construction".
    ("int-above-range", lambda: {"n": 9007199254740992}),
    ("int-below-range", lambda: {"n": -9007199254740992}),
    ("float", lambda: {"n": 1.5}),
    ("decimal-nan", lambda: {"n": Decimal("NaN")}),
    ("set", lambda: {"s": {1, 2}}),
    ("int-enum", lambda: {"e": _Color.RED}),
    ("str-enum", lambda: {"e": _Side.BUY}),
    ("int-key", lambda: {1: "a"}),
    ("duplicate-pair-key", lambda: [("a", 1), ("a", 2)]),
    # Keys.
    ("surrogate-key", lambda: {"\ud800": 1}),
    ("str-subclass-key", lambda: {_Str("a"): 1}),
    ("nested-int-above-range", lambda: {"a": {"b": 2**53}}),
    ("nested-int-key", lambda: {"a": {1: "b"}}),
    # Top level that is neither a dict, a Payload nor a list or tuple of pairs.
    ("top-none", lambda: None),
    ("top-str", lambda: "ab"),
    ("top-list-of-str", lambda: ["ab"]),
    ("top-triple", lambda: [("a", 1, 2)]),
    ("top-list-pair", lambda: [["a", 1]]),
    ("top-namedtuple-pair", lambda: [_Pair("a", 1)]),
    ("top-str-subclass-pair-key", lambda: [(_Str("a"), 1)]),
    ("top-int-pair-key", lambda: [(1, "a")]),
    ("top-generator-of-pairs", _generator_of_pairs),
    ("top-ordered-dict", lambda: OrderedDict(a=1)),
    ("top-mapping-proxy", lambda: MappingProxyType({"a": 1})),
    ("top-cyclic-dict", _cyclic_dict),
]

# Values that construction must reject wherever they appear (as a mapping value, a sequence element, at any depth).
REJECTED_VALUES: list[tuple[str, Callable[[], Any]]] = [
    ("bytes", lambda: b"a"),
    ("bytearray", lambda: bytearray(b"a")),
    ("float", lambda: 1.0),
    ("decimal-infinity", lambda: Decimal("Infinity")),
    ("decimal-negative-infinity", lambda: Decimal("-Infinity")),
    ("decimal-nan", lambda: Decimal("NaN")),
    ("decimal-negative-nan", lambda: Decimal("-NaN")),
    ("decimal-snan", lambda: Decimal("sNaN")),
    ("int-above-range", lambda: 2**53),
    ("int-below-range", lambda: -(2**53)),
    ("int-enum", lambda: _Color.RED),
    ("str-enum", lambda: _Side.BUY),
    ("str-subclass", lambda: _Str("a")),
    ("int-subclass", lambda: _Int(1)),
    ("decimal-subclass", lambda: _Decimal("1")),
    ("namedtuple", lambda: _Pair("a", 1)),
    ("list-subclass", lambda: _List([1])),
    ("dict-subclass", lambda: _Dict(a=1)),
    ("ordered-dict", lambda: OrderedDict(a=1)),
    ("defaultdict", lambda: defaultdict(int, a=1)),
    ("mapping-proxy", lambda: MappingProxyType({"a": 1})),
    ("set", lambda: {1}),
    ("frozenset", lambda: frozenset({1})),
    ("generator", _generator),
    ("iterator", lambda: iter([])),
    ("range", lambda: range(1)),
    ("object", lambda: object()),
    ("dataclass", lambda: _Point(1)),
    ("surrogate-string", lambda: "a\udfff"),
    ("cyclic-list", _cyclic_list),
]


def _permuted_mapping() -> dict[str, Any]:
    keys = [f"k{i:03d}" for i in range(200)]
    random.Random(0).shuffle(keys)
    return {key: index for index, key in enumerate(keys)}


def _nest(depth: int) -> dict[str, Any]:
    value: Any = 0
    for level in range(depth):
        value = [value] if level % 2 else {"n": value}
    return {"root": value}


# Sources that must construct and round-trip: the vectors plus edge cases of strings, decimals, size and depth.
CORPUS: list[tuple[str, Callable[[], Any]]] = [(name, build) for name, build, _ in VECTORS] + [
    ("non-ascii", lambda: {"š": "žluťoučký kůň € \U0001f600"}),
    ("nfc-and-nfd", lambda: {"nfc": "é", "nfd": "é"}),
    ("control-characters", lambda: {"c": "".join(chr(code) for code in range(0x20)) + "\x7f"}),
    ("decimal-60-nines", lambda: {"d": Decimal("9" * 60)}),
    ("decimal-huge-exponent", lambda: {"d": Decimal("1E+999999")}),
    ("decimal-tiny-exponent", lambda: {"d": Decimal("1E-999999")}),
    ("sequence-500", lambda: {"s": list(range(500))}),
    ("mapping-200-permuted", _permuted_mapping),
    ("nest-depth-50", lambda: _nest(50)),
]
