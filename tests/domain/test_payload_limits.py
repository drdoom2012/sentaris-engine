"""No implicit depth bound and cycle rejection at any depth (SE-2 spec 5.3, N11, N12, N17 (b))."""

import subprocess
import sys

import pytest

from sentaris_engine.domain.payload import FrozenMapping, decode_payload
from tests.domain.payload_helpers import REPO_ROOT, child_env

SHAPES = ("sequence", "mapping", "alternating")

# Cycle cases first, each reported and flushed as soon as known; the linear-cost case (N17 (b)) last.
SCRIPT = """
import sys
from sentaris_engine.domain.payload import FrozenMapping


def self_list():
    l = []
    l.append(l)
    FrozenMapping({"v": l})


def self_dict():
    d = {}
    d["a"] = d
    FrozenMapping(d)


def tuple_cycle():
    l = []
    l.append((l,))
    FrozenMapping({"v": l})


def indirect3():
    first = {}
    middle = []
    last = {}
    first["a"] = middle
    middle.append(last)
    last["b"] = first
    FrozenMapping({"v": first})


def diamond_back_edge():
    top = {}
    bottom = {}
    top["l"] = [bottom]
    top["r"] = [bottom]
    bottom["back"] = top
    FrozenMapping({"v": top})


def deep_cycle():
    first = []
    node = first
    for _ in range(max(10 * sys.getrecursionlimit(), 10_000)):
        child = []
        node.append(child)
        node = child
    node.append(first)
    FrozenMapping({"v": first})


def chain30():
    level = [1]
    for _ in range(30):
        level = [level, level]
    FrozenMapping({"c": level})


for case in (self_list, self_dict, tuple_cycle, indirect3, diamond_back_edge, deep_cycle, chain30):
    try:
        case()
        outcome = "OK"
    except Exception as error:
        outcome = type(error).__name__
    print(f"{case.__name__}:{outcome}", flush=True)
"""

EXPECTED_LINES = [
    "self_list:PayloadError",
    "self_dict:PayloadError",
    "tuple_cycle:PayloadError",
    "indirect3:PayloadError",
    "diamond_back_edge:PayloadError",
    "deep_cycle:PayloadError",
    "chain30:OK",
]


def test_cyclic_container_is_refused() -> None:
    try:
        completed = subprocess.run(
            [sys.executable, "-c", SCRIPT],
            cwd=REPO_ROOT,
            env=child_env(),
            check=False,
            timeout=20,
            capture_output=True,
            text=True,
        )
    except subprocess.TimeoutExpired as expired:
        partial = expired.stdout
        text = partial.decode(errors="replace") if isinstance(partial, bytes) else (partial or "")
        pytest.fail(f"cycle subprocess did not finish within 20 s; output so far:\n{text}")
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.splitlines() == EXPECTED_LINES


@pytest.fixture(scope="module")
def depth() -> int:
    return max(10 * sys.getrecursionlimit(), 10_000)


def _build(shape: str, depth: int) -> object:
    """Source nested `depth` levels below the top-level key "a", built iteratively, with leaf 1."""
    node: object = 1
    for level in range(depth):
        if shape == "sequence" or (shape == "alternating" and level % 2 == 0):
            node = [node]
        else:
            node = {"a": node}
    return {"a": node}


@pytest.fixture(scope="module")
def deep_payloads(depth: int) -> dict[str, FrozenMapping]:
    return {shape: FrozenMapping(_build(shape, depth)) for shape in SHAPES}


@pytest.fixture(scope="module")
def deep_copies(depth: int) -> dict[str, FrozenMapping]:
    return {shape: FrozenMapping(_build(shape, depth)) for shape in SHAPES}


@pytest.mark.parametrize("shape", SHAPES)
def test_no_implicit_depth_bound(
    shape: str, depth: int, deep_payloads: dict[str, FrozenMapping], deep_copies: dict[str, FrozenMapping]
) -> None:
    p = deep_payloads[shape]
    p_copy = deep_copies[shape]
    b = p.canonical_bytes()
    assert b.startswith(b'{"$map":{"a":')
    assert p == p_copy
    assert p_copy.canonical_bytes() == b
    assert hash(p) == hash(p_copy)
    assert repr(p).startswith("FrozenMapping(")
    q = decode_payload(b)
    assert q == p
    assert q.canonical_bytes() == b
    node: object = deep_payloads[shape]["a"]
    for level in range(depth - 1, -1, -1):
        if shape == "sequence" or (shape == "alternating" and level % 2 == 0):
            assert type(node) is tuple
            assert len(node) == 1
            node = node[0]
        else:
            assert type(node) is FrozenMapping
            assert list(node) == ["a"]
            node = node["a"]
    assert type(node) is int
    assert node == 1
