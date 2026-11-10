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
