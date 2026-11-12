"""Iterative helpers, A.3 vectors and seeded generators for the payload tests (SE-2 spec 5.3, 8.1).

No helper recurses over the payload structure (SE-2 spec 5.3).
"""

import os
import random
from collections.abc import Callable
from decimal import ROUND_DOWN, Context, Decimal
from pathlib import Path

from sentaris_engine.domain.payload import MAX_INT, FrozenMapping

# A.3, in order: the Python sources as written there (non-ASCII as escapes) and their canonical bytes.
VECTORS: list[tuple[object, bytes]] = [
    ({}, b'{"$map":{}}'),
    ({"b": 1, "a": True}, b'{"$map":{"a":true,"b":1}}'),
    (
        {"p": Decimal("64210.50"), "q": Decimal("-0"), "r": Decimal("1E+2"), "s": Decimal("0.0000001")},
        b'{"$map":{"p":{"$decimal":"64210.50"},"q":{"$decimal":"-0"},"r":{"$decimal":"1E+2"},"s":{"$decimal":"1E-7"}}}',
    ),
    ({"x": None, "y": [], "z": ["1", 1, None, {}]}, b'{"$map":{"x":null,"y":[],"z":["1",1,null,{"$map":{}}]}}'),
    ({"$map": "k", "\u00e9": 'a"b\\c\n\x01'}, b'{"$map":{"$map":"k","\xc3\xa9":"a\\"b\\\\c\\n\\u0001"}}'),
    ({"Z": 0, "a": -5, "ab": 2, "aa": 3}, b'{"$map":{"Z":0,"a":-5,"aa":3,"ab":2}}'),
    (
        {"max": 9007199254740991, "min": -9007199254740991},
        b'{"$map":{"max":9007199254740991,"min":-9007199254740991}}',
    ),
    ({"d": Decimal("-1.50E-12"), "t": (True, False)}, b'{"$map":{"d":{"$decimal":"-1.50E-12"},"t":[true,false]}}'),
]


def _leaf(value: object) -> tuple[object, ...] | None:
    """Tagged form of a scalar or `None`; None for a container."""
    if value is None:
        return ("none",)
    if type(value) is bool:
        return ("bool", value)
    if type(value) is int:
        return ("int", value)
    if type(value) is str:
        return ("str", value)
    if type(value) is Decimal:
        return ("dec", value.as_tuple())
    return None


def _children(value: object) -> tuple[list[str] | None, list[object]]:
    """Keys (None for a sequence) and children of a container, mapping keys sorted."""
    if type(value) is list or type(value) is tuple:
        return None, list(value)
    if type(value) is dict or type(value) is FrozenMapping:
        keys = sorted(value)
        return keys, [value[key] for key in keys]
    raise TypeError(f"not a payload or source value: {type(value).__name__}")


def tagged(value: object) -> object:
    """Type-tagged tree of plain tuples for a frozen or a source value, compared with `==`."""
    leaf = _leaf(value)
    if leaf is not None:
        return leaf
    stack: list[tuple[list[str] | None, list[object], list[object]]] = [(*_children(value), [])]
    while True:
        keys, children, done = stack[-1]
        if len(done) < len(children):
            child = children[len(done)]
            child_leaf = _leaf(child)
            if child_leaf is not None:
                done.append(child_leaf)
            else:
                stack.append((*_children(child), []))
            continue
        stack.pop()
        node = ("seq", tuple(done)) if keys is None else ("map", tuple(zip(keys, done, strict=True)))
        if not stack:
            return node
        stack[-1][2].append(node)


def reachable_values(p: FrozenMapping) -> list[object]:
    """Every key and value reachable from `p` through `items()` and tuple elements."""
    found: list[object] = []
    pending: list[object] = [p]
    while pending:
        current = pending.pop()
        if type(current) is FrozenMapping:
            for key, value in current.items():
                found.extend((key, value))
                pending.append(value)
        elif type(current) is tuple:
            found.extend(current)
            pending.extend(current)
    return found


def decimal_class(d: Decimal) -> str:
    """The SE-2 spec 5.4 case of a finite `d`: "e0", "plain", "leading_zeros", "sci_small" or "sci_positive"."""
    _, digits, exponent = d.as_tuple()
    if type(exponent) is not int:
        raise TypeError("not a finite Decimal")
    adjusted = exponent + len(digits) - 1
    if exponent == 0:
        return "e0"
    if exponent > 0:
        return "sci_positive"
    if adjusted < -6:
        return "sci_small"
    return "plain" if -exponent < len(digits) else "leading_zeros"


def _random_decimal(rng: random.Random) -> Decimal:
    sign = rng.randint(0, 1)
    if rng.random() < 0.1:
        digits: tuple[int, ...] = (0,)
    else:
        length = rng.randint(1, 25)
        digits = (rng.randint(1, 9), *(rng.randint(0, 9) for _ in range(length - 1)))
    return Decimal((sign, digits, rng.randint(-30, 30)))


def generated_decimals(seed: int, count: int) -> list[Decimal]:
    """`count` finite Decimals from `random.Random(seed)` (SE-2 spec 8.1)."""
    rng = random.Random(seed)
    return [_random_decimal(rng) for _ in range(count)]


# Every A.2 escape class, U+007F and non-ASCII (BMP and astral); written as escapes (plan Global Constraints).
STRING_POOL: list[str] = [
    *(chr(code) for code in range(0x20)),
    '"',
    "\\",
    "\x7f",
    "\u00e9",
    "\U0001f600",
    "",
    "plain",
    'a"b\\c\n\x01',
]
KEY_POOL: list[str] = ["$map", "$decimal", "\u00e9", "\U0001f600", "", "a", "ab", "b", "Z", "k\x00"]
_INTS: list[int] = [0, MAX_INT, -MAX_INT, -1, -2, -17, 1, 42]
_MAX_LEVEL = 4
_MAX_ENTRIES = 5


def _random_leaf(rng: random.Random) -> object:
    choice = rng.randint(0, 6)
    if choice == 0:
        return None
    if choice == 1:
        return rng.random() < 0.5
    if choice == 2:
        return rng.choice(_INTS)
    if choice == 3:
        return rng.randint(-MAX_INT, MAX_INT)
    if choice == 4:
        return rng.choice(STRING_POOL)
    if choice == 5:
        return Decimal("-0")
    return _random_decimal(rng)


def _generated_source(rng: random.Random) -> dict[str, object]:
    """One source of at most `_MAX_LEVEL` container levels, built iteratively.

    Every sequence is first a `list`; those chosen to be tuples are converted children-first afterwards.
    """
    root: dict[str, object] = {}
    pending: list[tuple[list[object] | dict[str, object], int]] = [(root, 1)]
    to_tuple: list[tuple[list[object] | dict[str, object], int | str, list[object]]] = []
    while pending:
        container, level = pending.pop()
        count = rng.randint(0, _MAX_ENTRIES)
        values: list[object] = []
        for _ in range(count):
            if level < _MAX_LEVEL and rng.random() < 0.35:
                child: list[object] | dict[str, object] = [] if rng.random() < 0.5 else {}
                pending.append((child, level + 1))
                values.append(child)
            else:
                values.append(_random_leaf(rng))
        slots: list[int | str]
        if type(container) is list:
            container.extend(values)
            slots = list(range(count))
        else:
            assert type(container) is dict
            keys = rng.sample(KEY_POOL, count)  # distinct keys, inserted in random order
            for key, value in zip(keys, values, strict=True):
                container[key] = value
            slots = list(keys)
        for slot, value in zip(slots, values, strict=True):
            if type(value) is list and rng.random() < 0.5:
                to_tuple.append((container, slot, value))
    # A child is recorded after its parent, so the reverse order converts every child before its parent.
    for parent, slot, sequence in reversed(to_tuple):
        if type(parent) is list:
            assert type(slot) is int
            parent[slot] = tuple(sequence)
        else:
            assert type(parent) is dict and type(slot) is str
            parent[slot] = tuple(sequence)
    return root


def generated_payloads(seed: int, count: int) -> list[FrozenMapping]:
    """`count` payloads from `random.Random(seed)` (SE-2 spec 8.1, AC-8)."""
    rng = random.Random(seed)
    return [FrozenMapping(_generated_source(rng)) for _ in range(count)]


# Altered `decimal` contexts of SE-2 spec section 6, `capitals = 0` first.
ALTERED_CONTEXTS: list[Context] = [
    Context(capitals=0),
    Context(prec=1),
    Context(rounding=ROUND_DOWN),
    Context(Emax=10, Emin=-10),
    Context(traps=[]),
]
ALTERED_CONTEXT_IDS: list[str] = ["capitals0", "prec1", "round_down", "emax_emin", "no_traps"]


# Shared references without a cycle (N17): each builder returns (shared source, separate copies).
def _siblings() -> tuple[object, object]:
    shared = [1, 2]
    return {"a": shared, "b": shared}, {"a": [1, 2], "b": [1, 2]}


def _list_elements() -> tuple[object, object]:
    shared = {"x": 1}
    return {"l": [shared, shared]}, {"l": [{"x": 1}, {"x": 1}]}


def _diamond() -> tuple[object, object]:
    bottom = [1]
    return {"p": {"q": bottom}, "r": [bottom]}, {"p": {"q": [1]}, "r": [[1]]}


def _different_depths() -> tuple[object, object]:
    shared = {"k": "v"}
    return {"a": shared, "b": [[shared]]}, {"a": {"k": "v"}, "b": [[{"k": "v"}]]}


def _shared_in_shared() -> tuple[object, object]:
    inner = [1]
    outer = [inner, inner]
    return {"a": outer, "b": outer}, {"a": [[1], [1]], "b": [[1], [1]]}


SHARED_CASES: dict[str, Callable[[], tuple[object, object]]] = {
    "siblings": _siblings,
    "list_elements": _list_elements,
    "diamond": _diamond,
    "different_depths": _different_depths,
    "shared_in_shared": _shared_in_shared,
}


REPO_ROOT = Path(__file__).resolve().parents[2]


def child_env(**extra: str) -> dict[str, str]:
    """Environment for a test subprocess: the repository and `src` on `PYTHONPATH`, no `PYTHONSAFEPATH`."""
    env = dict(os.environ)
    env.pop("PYTHONSAFEPATH", None)
    env["PYTHONPATH"] = os.pathsep.join([str(REPO_ROOT), str(REPO_ROOT / "src")])
    env.update(extra)
    return env
