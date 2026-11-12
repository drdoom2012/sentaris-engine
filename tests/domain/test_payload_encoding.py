"""Canonical form, equality, hash and repr (A.2, A.3; SE-2 spec 5.2, 5.4, N5, N7, N8, N10, N13, N14, N17)."""

import itertools
import subprocess
import sys
from collections.abc import Callable
from decimal import Context, Decimal, localcontext

import pytest

from sentaris_engine.domain.payload import FrozenMapping
from tests.domain.payload_helpers import (
    ALTERED_CONTEXT_IDS,
    ALTERED_CONTEXTS,
    REPO_ROOT,
    SHARED_CASES,
    VECTORS,
    child_env,
    decimal_class,
    generated_decimals,
    generated_payloads,
)

# The texts of the Decimal values in A.3.
A3_DECIMAL_TEXTS = ["64210.50", "-0", "1E+2", "0.0000001", "-1.50E-12"]

# Source text and its expected `$decimal` text: A.3, the SE-2 spec 5.4 examples and boundary values.
DECIMAL_TEXTS: list[tuple[str, str]] = [
    ("64210.50", "64210.50"),
    ("-0", "-0"),
    ("1E+2", "1E+2"),
    ("0.0000001", "1E-7"),
    ("-1.50E-12", "-1.50E-12"),
    ("100", "100"),
    ("1.00E+2", "100"),
    ("0.0005", "0.0005"),
    ("0E-3", "0.000"),
    ("0E+3", "0E+3"),
    ("0.000001", "0.000001"),
    ("0.000001234", "0.000001234"),
    ("12E-8", "1.2E-7"),
]


_PREFIX = b'{"$map":{"d":{"$decimal":"'
_SUFFIX = b'"}}}'


def _decimal_text(d: Decimal) -> str:
    """The `$decimal` text in the canonical bytes of `{"d": d}`."""
    data = FrozenMapping({"d": d}).canonical_bytes()
    assert data.startswith(_PREFIX)
    assert data.endswith(_SUFFIX)
    return data[len(_PREFIX) : -len(_SUFFIX)].decode("ascii")


@pytest.mark.parametrize(("source", "expected"), VECTORS, ids=[f"a3_{i}" for i in range(len(VECTORS))])
def test_vectors_encode(source: object, expected: bytes) -> None:
    assert FrozenMapping(source).canonical_bytes() == expected


def test_bool_is_not_integer() -> None:
    assert FrozenMapping({"a": True}).canonical_bytes() == b'{"$map":{"a":true}}'
    assert FrozenMapping({"a": False}).canonical_bytes() == b'{"$map":{"a":false}}'
    assert FrozenMapping({"a": 1}).canonical_bytes() == b'{"$map":{"a":1}}'
    assert FrozenMapping({"a": 0}).canonical_bytes() == b'{"$map":{"a":0}}'


def test_decimal_text_matches_default_str() -> None:
    generated = generated_decimals(seed=2, count=1000)
    with localcontext(Context()):
        for source, expected in DECIMAL_TEXTS:
            d = Decimal(source)
            assert _decimal_text(d) == expected
            assert _decimal_text(d) == str(d)
        for d in generated:
            assert _decimal_text(d) == str(d)
    assert {decimal_class(d) for d in generated} == {"e0", "plain", "leading_zeros", "sci_small", "sci_positive"}
    zeros = [d.as_tuple() for d in generated if d.as_tuple().digits == (0,)]
    assert any(type(t.exponent) is int and t.exponent > 0 for t in zeros)
    assert any(type(t.exponent) is int and t.exponent < 0 for t in zeros)
    assert any(t.sign == 1 for t in zeros)


def _context_samples() -> list[bytes]:
    """Construction and encoding of the A.3 decimal vectors and the generated set, under the current context."""
    sources: list[object] = [{"d": Decimal(text)} for text in A3_DECIMAL_TEXTS]
    sources.append(
        {"p": Decimal("64210.50"), "q": Decimal("-0"), "r": Decimal("1E+2"), "s": Decimal("0.0000001")},
    )
    sources.append({"d": Decimal("-1.50E-12"), "t": (True, False)})
    sources.extend({"d": d} for d in generated_decimals(seed=2, count=1000))
    return [FrozenMapping(source).canonical_bytes() for source in sources]


@pytest.mark.parametrize("ctx", ALTERED_CONTEXTS, ids=ALTERED_CONTEXT_IDS)
def test_decimal_text_ignores_context(ctx: Context) -> None:
    with localcontext(Context()):
        expected = _context_samples()
    with localcontext(ctx):
        altered = _context_samples()
    assert altered == expected
    assert expected[5] == VECTORS[2][1]
    assert expected[6] == VECTORS[7][1]


SHORT_ESCAPES = {0x08: b"\\b", 0x09: b"\\t", 0x0A: b"\\n", 0x0C: b"\\f", 0x0D: b"\\r"}


def _expected_escape(ch: str) -> bytes:
    """The A.2 string-row encoding of one character, built from the table."""
    code = ord(ch)
    if ch == '"':
        return b'\\"'
    if ch == "\\":
        return b"\\\\"
    if code in SHORT_ESCAPES:
        return SHORT_ESCAPES[code]
    if code < 0x20:
        return b"\\u00" + f"{code:02x}".encode("ascii")
    return ch.encode("utf-8")


ESCAPE_CHARS = [chr(code) for code in range(0x20)] + ['"', "\\", "\x7f", "\u00e9", "\U0001f600"]


@pytest.mark.parametrize("ch", ESCAPE_CHARS, ids=[f"U+{ord(c):04X}" for c in ESCAPE_CHARS])
def test_string_escaping(ch: str) -> None:
    escaped = _expected_escape(ch)
    assert FrozenMapping({"a": ch}).canonical_bytes() == b'{"$map":{"a":"' + escaped + b'"}}'
    assert FrozenMapping({ch: 1}).canonical_bytes() == b'{"$map":{"' + escaped + b'":1}}'


def test_string_escaping_literal_expectations() -> None:
    assert FrozenMapping({"a": "\x1f"}).canonical_bytes() == b'{"$map":{"a":"\\u001f"}}'
    assert FrozenMapping({"a": "\x08"}).canonical_bytes() == b'{"$map":{"a":"\\b"}}'
    assert FrozenMapping({"a": "\x7f"}).canonical_bytes() == b'{"$map":{"a":"\x7f"}}'
    assert FrozenMapping({"a": "\U0001f600"}).canonical_bytes() == b'{"$map":{"a":"\xf0\x9f\x98\x80"}}'


def test_key_order_is_by_code_point() -> None:
    p = FrozenMapping({"b": 1, "ab": 2, "a": 3, "Z": 4, "\uffff": 5, "\U0001f600": 6})
    assert list(p) == ["Z", "a", "ab", "b", "\uffff", "\U0001f600"]
    assert p.canonical_bytes() == (b'{"$map":{"Z":4,"a":3,"ab":2,"b":1,"\xef\xbf\xbf":5,"\xf0\x9f\x98\x80":6}}')


ENTRIES: list[tuple[str, object]] = [("b", 1), ("a", [1, "x"]), ("Z", Decimal("1.0")), ("\U0001f600", {"k": None})]


def test_construction_order_does_not_change_form_or_iteration() -> None:
    reference = FrozenMapping(dict(ENTRIES))
    expected_bytes = reference.canonical_bytes()
    expected_keys = list(reference)
    assert expected_keys == ["Z", "a", "b", "\U0001f600"]
    for order in itertools.permutations(ENTRIES):
        for p in (FrozenMapping(dict(order)), FrozenMapping(list(order))):
            assert p.canonical_bytes() == expected_bytes
            assert list(p) == expected_keys


def _pairwise_unequal(values: list[object]) -> None:
    payloads = [FrozenMapping({"v": v}) for v in values]
    for i, j in itertools.combinations(range(len(payloads)), 2):
        assert payloads[i] != payloads[j]
        assert (payloads[i] == payloads[j]) is False


EQUAL_PAIRS: dict[str, Callable[[], tuple[FrozenMapping, FrozenMapping]]] = {
    "list_tuple": lambda: (FrozenMapping({"s": [1, 2]}), FrozenMapping({"s": (1, 2)})),
    "insertion_order": lambda: (FrozenMapping({"a": 1, "b": 2}), FrozenMapping({"b": 2, "a": 1})),
    "dict_pairs": lambda: (FrozenMapping({"a": {"x": 1}}), FrozenMapping([("a", FrozenMapping([("x", 1)]))])),
    "same_source": lambda: (FrozenMapping({"d": Decimal("1.0")}), FrozenMapping({"d": Decimal("1.0")})),
}


def test_equality_is_by_canonical_form() -> None:
    assert FrozenMapping({"a": True}) != FrozenMapping({"a": 1})
    _pairwise_unequal([Decimal("1.0"), Decimal("1.00"), Decimal("1E+1")])
    _pairwise_unequal([Decimal(0), Decimal("-0")])
    _pairwise_unequal(["1", 1, True, Decimal(1), None])
    for make in EQUAL_PAIRS.values():
        first, second = make()
        assert first == second
        assert (first != second) is False
    assert (FrozenMapping({}) == {}) is False
    assert (FrozenMapping({}) != {}) is True


@pytest.mark.parametrize("make", EQUAL_PAIRS.values(), ids=EQUAL_PAIRS.keys())
def test_hash_follows_equality(make: Callable[[], tuple[FrozenMapping, FrozenMapping]]) -> None:
    first, second = make()
    assert first == second
    assert hash(first) == hash(second)


@pytest.mark.parametrize("make", SHARED_CASES.values(), ids=SHARED_CASES.keys())
def test_shared_container_is_accepted_bytes(make: Callable[[], tuple[object, object]]) -> None:
    shared, copied = make()
    p = FrozenMapping(shared)
    q = FrozenMapping(copied)
    assert p.canonical_bytes() == q.canonical_bytes()
    assert p == q
    assert hash(p) == hash(q)


def test_repr_shows_canonical_form() -> None:
    assert repr(FrozenMapping({"a": 1})) == 'FrozenMapping({"$map":{"a":1}})'


def test_canonical_form_is_cached_on_the_requested_mapping_only() -> None:
    inner = FrozenMapping({"x": 1})
    outer = FrozenMapping({"a": {"b": 2}, "i": inner})
    nested = outer["a"]
    assert type(nested) is FrozenMapping
    data = outer.canonical_bytes()
    assert outer.canonical_bytes() is data
    assert outer._bytes is data
    assert nested._bytes is None
    assert inner._bytes is None


SCRIPT = """
from tests.domain.payload_helpers import VECTORS, generated_payloads
from sentaris_engine.domain.payload import FrozenMapping

for source, _ in VECTORS:
    print(FrozenMapping(source).canonical_bytes().hex())
for p in generated_payloads(seed=1, count=50):
    print(p.canonical_bytes().hex())
"""


def test_canonical_form_is_identical_across_processes() -> None:
    expected = [FrozenMapping(source).canonical_bytes().hex() for source, _ in VECTORS]
    expected += [p.canonical_bytes().hex() for p in generated_payloads(seed=1, count=50)]
    outputs = []
    for seed in ("0", "1"):
        completed = subprocess.run(
            [sys.executable, "-c", SCRIPT],
            cwd=REPO_ROOT,
            env=child_env(PYTHONHASHSEED=seed),
            check=False,
            timeout=60,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr
        outputs.append(completed.stdout.splitlines())
    assert outputs[0] == outputs[1]
    assert outputs[0] == expected
