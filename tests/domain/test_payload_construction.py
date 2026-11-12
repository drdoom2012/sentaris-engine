"""Payload construction: accepted values, source shapes, freezing, shared references (A.1; SE-2 spec 5.1, N1-N4, N15, N17)."""

from collections import OrderedDict
from collections.abc import Callable, Iterator
from decimal import Decimal
from enum import Enum, IntEnum
from types import MappingProxyType

import pytest

from sentaris_engine.domain.payload import MAX_INT, FrozenMapping, PayloadError, is_payload_scalar
from tests.domain.payload_helpers import SHARED_CASES, reachable_values, tagged


class _Int(IntEnum):
    ONE = 1


class _Str(str, Enum):
    A = "a"


class _Plain(Enum):
    A = "a"


class _StrSub(str):
    pass


class _IntSub(int):
    pass


class _DecimalSub(Decimal):
    pass


class _DictSub(dict[str, object]):
    pass


class _ListSub(list[object]):
    pass


class _TupleSub(tuple[object, ...]):
    pass


def _generator() -> Iterator[int]:
    yield 1


FROZEN_TYPES = {type(None), bool, int, str, Decimal, tuple, FrozenMapping}


SCALARS: list[object] = [True, False, 0, MAX_INT, -MAX_INT, "", "\u00e9", Decimal("1.0"), Decimal("-0")]
NOT_SCALARS: list[object] = [
    None,
    (),
    [],
    {},
    FrozenMapping({}),
    MAX_INT + 1,
    -MAX_INT - 1,
    1.5,
    Decimal("NaN"),
    Decimal("sNaN"),
    Decimal("Infinity"),
    Decimal("-Infinity"),
    "\ud800",
    "a\udfff",
    b"x",
    bytearray(b"x"),
    _Int.ONE,
    _Str.A,
    _Plain.A,
    _StrSub("a"),
    _IntSub(1),
    _DecimalSub("1"),
    object(),
]


@pytest.mark.parametrize(
    ("value", "expected"),
    [(v, True) for v in SCALARS] + [(v, False) for v in NOT_SCALARS],
    ids=[f"scalar{i}-{type(v).__name__}" for i, v in enumerate(SCALARS)]
    + [f"not_scalar{i}-{type(v).__name__}" for i, v in enumerate(NOT_SCALARS)],
)
def test_scalar_predicate(value: object, expected: bool) -> None:
    assert is_payload_scalar(value) is expected


# Factories, so that single-use values (generator, iterator) are fresh in every case.
REJECTED_VALUES: dict[str, Callable[[], object]] = {
    "float": lambda: 1.5,
    "decimal_nan": lambda: Decimal("NaN"),
    "decimal_snan": lambda: Decimal("sNaN"),
    "decimal_infinity": lambda: Decimal("Infinity"),
    "decimal_minus_infinity": lambda: Decimal("-Infinity"),
    "int_above_range": lambda: 2**53,
    "int_below_range": lambda: -(2**53),
    "bytes": lambda: b"x",
    "bytearray": lambda: bytearray(b"x"),
    "int_enum": lambda: _Int.ONE,
    "str_enum": lambda: _Str.A,
    "plain_enum": lambda: _Plain.A,
    "str_subclass": lambda: _StrSub("a"),
    "int_subclass": lambda: _IntSub(1),
    "decimal_subclass": lambda: _DecimalSub("1"),
    "dict_subclass": lambda: _DictSub(),
    "list_subclass": lambda: _ListSub(),
    "tuple_subclass": lambda: _TupleSub(),
    "set": lambda: {1},
    "frozenset": lambda: frozenset({1}),
    "generator": _generator,
    "iterator": lambda: iter([1]),
    "range": lambda: range(1),
    "object": object,
    "mapping_proxy": lambda: MappingProxyType({}),
    "ordered_dict": lambda: OrderedDict(),
    "surrogate_str": lambda: "\ud800",
    "trailing_surrogate_str": lambda: "a\udfff",
}

WRAPPERS: dict[str, Callable[[object], object]] = {
    "top_level_value": lambda x: {"v": x},
    "in_list": lambda x: {"v": [x]},
    "in_tuple": lambda x: {"v": (x,)},
    "in_nested_dict": lambda x: {"v": {"w": x}},
    "in_nested_frozen_mapping": lambda x: {"v": FrozenMapping({"w": x})},
}

BAD_KEYS: dict[str, Callable[[], object]] = {
    "int": lambda: 1,
    "bool": lambda: True,
    "none": lambda: None,
    "str_subclass": lambda: _StrSub("k"),
    "surrogate": lambda: "\ud800",
}


KEY_POSITIONS = ("top_level", "nested_dict", "nested_frozen_mapping")


def _bad_key_source(make: Callable[[], object], position: str) -> Callable[[], object]:
    def build() -> object:
        source: dict[object, object] = {make(): 1}
        if position == "nested_dict":
            return {"v": source}
        if position == "nested_frozen_mapping":
            return {"v": FrozenMapping(source)}
        return source

    return build


def _wrapped(make: Callable[[], object], wrap: Callable[[object], object]) -> Callable[[], object]:
    return lambda: wrap(make())


# Built lazily: the nested-FrozenMapping wrapper raises while the source is being built, inside pytest.raises.
REJECTED_SOURCES: dict[str, Callable[[], object]] = {
    **{
        f"{value_id}-{wrap_id}": _wrapped(make, wrap)
        for value_id, make in REJECTED_VALUES.items()
        for wrap_id, wrap in WRAPPERS.items()
    },
    **{
        f"key_{key_id}-{position}": _bad_key_source(make, position)
        for key_id, make in BAD_KEYS.items()
        for position in KEY_POSITIONS
    },
}


@pytest.mark.parametrize("make_source", REJECTED_SOURCES.values(), ids=REJECTED_SOURCES.keys())
def test_rejected_value_is_refused(make_source: Callable[[], object]) -> None:
    with pytest.raises(PayloadError):
        FrozenMapping(make_source())


BAD_SOURCES: dict[str, Callable[[], object]] = {
    "int": lambda: 1,
    "str": lambda: "a",
    "none": lambda: None,
    "set": lambda: {1, 2},
    "generator_of_pairs": lambda: (p for p in [("a", 1)]),
    "list_of_scalar": lambda: [1],
    "list_pair": lambda: [["a", 1]],
    "pair_of_length_1": lambda: [("a",)],
    "pair_of_length_3": lambda: [("a", 1, 2)],
    "pair_with_int_key": lambda: [(1, "a")],
    "ordered_dict": lambda: OrderedDict(),
    "mapping_proxy": lambda: MappingProxyType({}),
}


@pytest.mark.parametrize("make", BAD_SOURCES.values(), ids=BAD_SOURCES.keys())
def test_bad_source_is_refused(make: Callable[[], object]) -> None:
    with pytest.raises(PayloadError):
        FrozenMapping(make())


def test_empty_pairs_give_empty_mapping() -> None:
    assert len(FrozenMapping([])) == 0
    assert len(FrozenMapping(())) == 0


DUPLICATE_KEY_SOURCES: dict[str, Callable[[], object]] = {
    "adjacent": lambda: [("a", 1), ("a", 2)],
    "separated_equal_values": lambda: [("a", 1), ("b", 2), ("a", 1)],
    "nested_pair_mapping": lambda: {"v": FrozenMapping([("k", 1), ("k", 1)])},
}


@pytest.mark.parametrize("make_source", DUPLICATE_KEY_SOURCES.values(), ids=DUPLICATE_KEY_SOURCES.keys())
def test_duplicate_key_from_pairs_is_refused(make_source: Callable[[], object]) -> None:
    with pytest.raises(PayloadError):
        FrozenMapping(make_source())


def test_source_mutation_does_not_change_payload() -> None:
    source: dict[str, object] = {"a": [1, 2], "b": "x"}
    untouched: dict[str, object] = {"a": [1, 2], "b": "x"}
    p = FrozenMapping(source)
    inner = source["a"]
    assert type(inner) is list
    inner.append(3)
    source["b"] = "y"
    del source["a"]
    assert tagged(p) == tagged(untouched)

    pairs: list[tuple[str, object]] = [("a", [1])]
    untouched_pairs: list[tuple[str, object]] = [("a", [1])]
    q = FrozenMapping(pairs)
    pair_value = pairs[0][1]
    assert type(pair_value) is list
    pair_value.append(2)
    pairs[0] = ("z", 0)
    del pairs[0]
    assert tagged(q) == tagged(FrozenMapping(untouched_pairs))


def test_no_mutable_value_is_reachable() -> None:
    every_kind: dict[str, object] = {
        "n": None,
        "b": True,
        "i": 1,
        "s": "x",
        "d": Decimal("1.5"),
        "l": [1],
        "t": (2,),
        "m": {"k": None},
        "f": FrozenMapping({"x": [1]}),
    }
    p = FrozenMapping({"one": [({"two": [every_kind, (every_kind,)]},)], "three": {"four": {"five": every_kind}}})
    values = reachable_values(p)
    assert len(values) > 0
    assert all(type(v) in FROZEN_TYPES for v in values)


def test_mapping_cannot_be_mutated() -> None:
    p = FrozenMapping({"a": 1})
    with pytest.raises(TypeError):
        p["a"] = 1  # type: ignore[index]
    with pytest.raises(TypeError):
        del p["a"]  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        p.x = 1
    with pytest.raises(AttributeError):
        del p._items
    assert not hasattr(p, "__dict__")


def test_mapping_cannot_be_reinitialised() -> None:
    p = FrozenMapping({"a": 1})
    with pytest.raises(TypeError):
        FrozenMapping.__init__(p, {"b": 2})
    assert list(p) == ["a"]
    assert p["a"] == 1
    built = FrozenMapping({"n": {"x": 1}})["n"]
    assert type(built) is FrozenMapping
    with pytest.raises(TypeError):
        FrozenMapping.__init__(built, {"y": 2})
    assert list(built) == ["x"]


def test_mapping_cannot_be_subclassed() -> None:
    with pytest.raises(TypeError):

        class Sub(FrozenMapping):  # type: ignore[misc]
            pass


@pytest.mark.parametrize(
    "source",
    [{"b": 1, "a": 2, "Z": 3}, [("b", 1), ("Z", 3), ("a", 2)]],
    ids=["dict", "pairs"],
)
def test_iteration_is_in_code_point_order(source: object) -> None:
    assert list(FrozenMapping(source)) == ["Z", "a", "b"]


def test_list_becomes_tuple() -> None:
    outer = FrozenMapping({"a": [1, [2]]})["a"]
    assert tagged(outer) == ("seq", (("int", 1), ("seq", (("int", 2),))))
    assert type(outer) is tuple
    assert type(outer[1]) is tuple

    nested_pairs = FrozenMapping({"a": [("k", 1)]})["a"]
    assert type(nested_pairs) is tuple
    assert type(nested_pairs[0]) is tuple
    assert tagged(nested_pairs[0]) == ("seq", (("str", "k"), ("int", 1)))


def test_frozen_value_is_reused() -> None:
    inner = FrozenMapping({"x": 1})
    assert FrozenMapping({"a": inner})["a"] is inner
    in_list = FrozenMapping({"a": [inner]})["a"]
    assert type(in_list) is tuple
    assert in_list[0] is inner
    assert FrozenMapping(inner)._items is inner._items


@pytest.mark.parametrize("make", SHARED_CASES.values(), ids=SHARED_CASES.keys())
def test_shared_container_is_accepted(make: Callable[[], tuple[object, object]]) -> None:
    shared, copied = make()
    p = FrozenMapping(shared)
    assert tagged(p) == tagged(FrozenMapping(copied))
    assert all(type(v) in FROZEN_TYPES for v in reachable_values(p))


def test_shared_container_is_frozen_once() -> None:
    level: list[object] = [1]
    for _ in range(4):
        level = [level, level]
    node = FrozenMapping({"c": level})["c"]
    for _ in range(4):
        assert type(node) is tuple
        assert node[0] is node[1]
        node = node[0]
    assert tagged(node) == ("seq", (("int", 1),))
