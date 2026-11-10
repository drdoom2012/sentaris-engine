import copy
import pickle
import sys
from collections.abc import Callable
from decimal import ROUND_DOWN, Context, Decimal, localcontext
from typing import Any, cast

import pytest

from sentaris_engine.domain.payload import MAX_SAFE_INT, Payload, PayloadError
from tests.support.vectors import REJECTED, REJECTED_VALUES, VECTORS


def _wrapped(build: Callable[[], Any]) -> Callable[[], Any]:
    return lambda: {"v": build()}


_ALL_REJECTED = [(name, build) for name, build in REJECTED] + [
    (f"value-{name}", _wrapped(build)) for name, build in REJECTED_VALUES
]


def _decimal_bytes(text: str) -> bytes:
    return b'{"$map":{"v":{"$decimal":"' + text.encode() + b'"}}}'


@pytest.mark.parametrize(("build", "expected"), [(b, e) for _, b, e in VECTORS], ids=[n for n, _, _ in VECTORS])
def test_vectors_encode_to_exact_bytes(build: Callable[[], Any], expected: bytes) -> None:
    assert Payload.of(build()).canonical() == expected


@pytest.mark.parametrize("build", [b for _, b in _ALL_REJECTED], ids=[n for n, _ in _ALL_REJECTED])
def test_rejected_sources_raise_payload_error(build: Callable[[], Any]) -> None:
    with pytest.raises(PayloadError):
        Payload.of(build())


def test_empty_pair_sources_are_valid() -> None:
    for payload in (Payload.of([]), Payload.of(()), Payload.of()):
        assert payload.canonical() == b'{"$map":{}}'


def test_integer_range_boundaries() -> None:
    assert MAX_SAFE_INT == 2**53 - 1
    assert Payload.of({"v": MAX_SAFE_INT}).canonical() == b'{"$map":{"v":9007199254740991}}'
    assert Payload.of({"v": -MAX_SAFE_INT}).canonical() == b'{"$map":{"v":-9007199254740991}}'
    for value in (2**53, -(2**53)):
        with pytest.raises(PayloadError):
            Payload.of({"v": value})
    assert Payload.of({"v": True}).canonical() == b'{"$map":{"v":true}}'
    assert Payload.of({"v": 1}).canonical() == b'{"$map":{"v":1}}'


def test_distinct_kinds_have_distinct_canonical_forms() -> None:
    values: list[object] = ["1", 1, True, Decimal(1), None]
    forms = {Payload.of({"v": value}).canonical() for value in values}
    assert len(forms) == 5


def test_decimal_exponent_is_identity() -> None:
    for left, right in ((Decimal("1.0"), Decimal("1.00")), (Decimal(0), Decimal("-0"))):
        a, b = Payload.of({"v": left}), Payload.of({"v": right})
        assert a != b
        assert a.canonical() != b.canonical()


def test_null_differs_from_absent_key() -> None:
    with_null, empty = Payload.of({"a": None}), Payload.of({})
    assert with_null != empty
    assert with_null.canonical() == b'{"$map":{"a":null}}'


def test_key_order_does_not_matter() -> None:
    forward = Payload.of({"b": 1, "a": 2, "\u00e9": 3, "B": 4})
    backward = Payload.of({"B": 4, "\u00e9": 3, "a": 2, "b": 1})
    pairs = Payload.of([("a", 2), ("\u00e9", 3), ("b", 1), ("B", 4)])
    assert forward == backward == pairs
    assert hash(forward) == hash(backward) == hash(pairs)
    assert forward.canonical() == backward.canonical() == pairs.canonical()
    assert list(forward) == ["B", "a", "b", "\u00e9"]


def test_equality_is_canonical_not_python() -> None:
    assert Payload.of({"a": 1}) != Payload.of({"a": True})
    assert Payload.of({"a": (Decimal("1.0"),)}) != Payload.of({"a": (Decimal("1.00"),)})


def test_nfc_and_nfd_strings_are_distinct() -> None:
    nfc, nfd = Payload.of({"v": "\u00e9"}), Payload.of({"v": "e\u0301"})
    assert nfc != nfd
    assert nfc.canonical() == b'{"$map":{"v":"\xc3\xa9"}}'
    assert nfd.canonical() == b'{"$map":{"v":"e\xcc\x81"}}'


def test_duplicate_pair_key_is_rejected() -> None:
    with pytest.raises(PayloadError):
        Payload.of([("a", 1), ("a", 2)])


def test_nested_pairs_stay_a_sequence() -> None:
    assert Payload.of({"s": [("a", 1)]}).canonical() == b'{"$map":{"s":[["a",1]]}}'


def test_mutable_inputs_are_copied() -> None:
    inner: dict[str, Any] = {"x": [1, 2]}
    items: list[Any] = [inner, 3]
    source: dict[str, Any] = {"items": items}
    unmutated = copy.deepcopy(source)
    payload = Payload.of(source)
    inner["x"].append(9)
    inner["y"] = 1
    items.append(4)
    source["new"] = 5
    frozen_items = payload["items"]
    assert type(frozen_items) is tuple
    frozen_inner = frozen_items[0]
    assert type(frozen_inner) is Payload
    assert type(frozen_inner["x"]) is tuple
    assert payload == Payload.of(unmutated)


def test_payload_cannot_be_mutated() -> None:
    payload = cast(Any, Payload.of({"m": {"a": 1}, "s": [1, 2]}))
    with pytest.raises(TypeError):
        payload["new"] = 1
    with pytest.raises(TypeError):
        payload["m"]["a"] = 2
    with pytest.raises(TypeError):
        payload["s"][0] = 3
    with pytest.raises(AttributeError):
        payload._items = 1
    with pytest.raises(AttributeError):
        del payload._items
    with pytest.raises(TypeError):
        cast(Any, Payload)({})
    assert type(payload["s"]) is tuple
    assert type(payload["m"]) is Payload
    assert payload == Payload.of({"m": {"a": 1}, "s": (1, 2)})


def test_copy_and_pickle_round_trip() -> None:
    payload = Payload.of({"m": {"a": Decimal("1.0")}, "s": [None, True, "x"]})
    assert copy.copy(payload) == payload
    assert copy.deepcopy(payload) == payload
    assert pickle.loads(pickle.dumps(payload)) == payload


def test_decimal_text_ignores_the_decimal_context() -> None:
    with localcontext() as context:
        context.capitals = 0
        context.prec = 2
        context.rounding = ROUND_DOWN
        for signal in context.traps:
            context.traps[signal] = True
        assert Payload.of({"v": Decimal("1E+2")}).canonical() == _decimal_bytes("1E+2")
        assert Payload.of({"v": Decimal("64210.50")}).canonical() == _decimal_bytes("64210.50")
        for _, build, expected in VECTORS:
            assert Payload.of(build()).canonical() == expected


@pytest.mark.parametrize(
    "text",
    [
        "0",
        "-0",
        "-0.00",
        "0E+2",
        "0E-7",
        "0.000001",
        "0.0000001",
        "123456789E+5",
        "1.50E-12",
        "1E+2",
        "-1E-7",
        "12345678901234567890.123",
        "1E+999999",
    ],
)
def test_decimal_text_equals_str_under_default_context(text: str) -> None:
    with localcontext(Context()):
        value = Decimal(text)
        assert Payload.of({"v": value}).canonical() == _decimal_bytes(str(value))


def test_deep_nesting_beyond_recursion_limit() -> None:
    depth = 5 * sys.getrecursionlimit()

    def build() -> dict[str, Any]:
        value: Any = None
        for level in range(depth):
            value = [value] if level % 2 else {"n": value}
        return {"root": value}

    payload, again = Payload.of(build()), Payload.of(build())
    form = payload.canonical()
    assert form.startswith(b'{"$map":{"root":') and form.count(b"[") == depth // 2
    assert payload == again
    assert hash(payload) == hash(again)
    assert payload != Payload.of({"root": None})


def test_of_accepts_typed_dicts_and_pairs_under_strict_mypy() -> None:
    # `dict` is invariant: these typed variables must type-check as `Payload.of` sources (covered by `make typecheck`).
    closes: dict[str, Decimal] = {"a": Decimal("1.0")}
    counts: dict[str, int] = {"a": 1, "b": 2}
    lists: dict[str, list[int]] = {"a": [1, 2]}
    pairs: list[tuple[str, int]] = [("b", 2), ("a", 1)]
    assert Payload.of(closes).canonical() == b'{"$map":{"a":{"$decimal":"1.0"}}}'
    assert Payload.of(counts) == Payload.of(pairs)
    assert Payload.of(lists).canonical() == b'{"$map":{"a":[1,2]}}'


def _all_slot_values(payload: Payload) -> list[tuple[str, object]]:
    return [(name, getattr(payload, name)) for name in Payload.__slots__ if hasattr(payload, name)]


def test_no_mutable_lookup_structure_is_reachable() -> None:
    payload = Payload.of({"a": 1, "b": [1, {"c": 2}], "d": {"e": None}})
    payload.canonical()
    assert not hasattr(payload, "__dict__")
    assert not hasattr(payload, "_index")
    for name, value in _all_slot_values(payload):
        assert type(value) not in (dict, list, set, bytearray), name
    inner = payload["d"]
    assert type(inner) is Payload
    for name, value in _all_slot_values(inner):
        assert type(value) not in (dict, list, set, bytearray), name
    # Nothing writable is left to change a lookup behind the payload's back.
    with pytest.raises(AttributeError):
        cast(Any, payload)._items = ()
    with pytest.raises(AttributeError):
        cast(Any, payload)._keys = ()
    with pytest.raises(AttributeError):
        cast(Any, payload)._index = {"a": 999}
    assert payload["a"] == 1
    assert dict(payload)["a"] == 1


def _text(*code_points: int) -> str:
    # `chr` rather than literal escapes: `ruff format` rewrites printable escapes into literal non-ASCII text.
    return "".join(chr(point) for point in code_points)


_A, _E_ACUTE, _CJK, _EMOJI = 0x61, 0xE9, 0x4E2D, 0x1F600
_LOOKUP_POINTS: list[tuple[int, ...]] = [
    (),
    (_A,),
    (_A, _A),
    (_A, _A, _A),
    (_A, 0x62),
    (_A, 0x62, 0x63),
    (0x62,),
    (0x62, _A),
    (_E_ACUTE,),
    (_E_ACUTE, _E_ACUTE),
    (0x65,),
    (0x65, 0x301),
    (0xFF,),
    (0x100,),
    (_CJK,),
    (_CJK, 0x6587),
    (0xD7FF,),
    (0xE000,),
    (0xFFFF,),
    (0x10000,),
    (_EMOJI,),
    (_EMOJI, _A),
    (0,),
    (0, 0),
]


_LOOKUP_KEYS = [_text(*points) for points in _LOOKUP_POINTS]


def test_lookup_keys_are_the_intended_ascii_escapes() -> None:
    assert [ascii(key) for key in _LOOKUP_KEYS[8:10]] == ["'\\xe9'", "'\\xe9\\xe9'"]
    assert ascii(_LOOKUP_KEYS[14]) == "'\\u4e2d'"
    assert ascii(_LOOKUP_KEYS[19]) == "'\\U00010000'"
    assert ascii(_LOOKUP_KEYS[21]) == "'\\U0001f600a'"
    assert len(set(_LOOKUP_KEYS)) == len(_LOOKUP_KEYS)


def test_lookup_finds_every_key_and_only_those() -> None:
    entries = [(key, index) for index, key in enumerate(_LOOKUP_KEYS)]
    for rotation in (0, 5, 11):
        rotated = entries[rotation:] + entries[:rotation]
        payload = Payload.of(rotated)
        for key, index in entries:
            assert payload[key] == index
            assert key in payload
            assert payload.get(key) == index
        assert list(payload) == sorted(_LOOKUP_KEYS)
        assert list(payload.items()) == sorted(entries)
        assert list(payload.values()) == [index for _, index in sorted(entries)]
        assert list(payload.keys()) == sorted(_LOOKUP_KEYS)
        assert len(payload) == len(entries)
    absent = ["\x01", "aaaa", "abcd", "b\x00", "bb", "c", _text(0xEA), _text(_E_ACUTE, _A), _text(0x4E2E)]
    absent += [_text(0x1F601), _text(0x10FFFF)]
    for key in absent:
        assert key not in payload, ascii(key)
        assert payload.get(key) is None
        with pytest.raises(KeyError):
            payload[key]
    for bad in (1, None, b"a", ("a",)):
        with pytest.raises(KeyError):
            payload[cast(Any, bad)]
        assert cast(Any, bad) not in payload


def test_lookup_in_a_large_payload_and_in_the_empty_payload() -> None:
    size = 2000
    payload = Payload.of({f"k{number}": number for number in range(size)})
    assert all(payload[f"k{number}"] == number for number in range(size))
    assert "k" not in payload and f"k{size}" not in payload and "k0\x00" not in payload
    assert len(Payload.of()) == 0 and "a" not in Payload.of()
    with pytest.raises(KeyError):
        Payload.of()["a"]


class _CountingKey(str):
    """A str that counts the comparisons made against it, to prove a lookup is a binary search."""

    comparisons = 0

    def _count(self) -> None:
        type(self).comparisons += 1

    def __lt__(self, other: str) -> bool:
        self._count()
        return str.__lt__(self, other)

    def __gt__(self, other: str) -> bool:
        self._count()
        return str.__gt__(self, other)

    def __le__(self, other: str) -> bool:
        self._count()
        return str.__le__(self, other)

    def __ge__(self, other: str) -> bool:
        self._count()
        return str.__ge__(self, other)

    def __eq__(self, other: object) -> bool:
        self._count()
        return str.__eq__(self, other)

    def __ne__(self, other: object) -> bool:
        self._count()
        return str.__ne__(self, other)

    __hash__ = str.__hash__


def test_lookup_makes_a_logarithmic_number_of_comparisons() -> None:
    size = 100_000
    payload = Payload.of({f"{number:06d}": number for number in range(size)})
    for probe, found in (("000000", True), ("049999", True), ("099999", True), ("050000x", False), ("zzzzzz", False)):
        _CountingKey.comparisons = 0
        key = _CountingKey(probe)
        assert (payload.get(key) is not None) is found
        assert _CountingKey.comparisons <= 2 * size.bit_length(), (probe, _CountingKey.comparisons)
