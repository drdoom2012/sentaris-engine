"""Strict canonical decoder and exception handling (A.2 "Required properties"; SE-2 spec 5.5, 5.6, N6, N9, N16)."""

import ast
from decimal import Clamped, Context, Decimal, Inexact, InvalidOperation, Overflow, Rounded, Underflow, localcontext
from pathlib import Path

import pytest

from sentaris_engine.domain import payload
from sentaris_engine.domain.payload import FrozenMapping, PayloadError, decode_payload
from tests.domain.payload_helpers import (
    ALTERED_CONTEXT_IDS,
    ALTERED_CONTEXTS,
    VECTORS,
    generated_payloads,
    reachable_values,
    tagged,
)

PAYLOAD_SOURCE = Path(payload.__file__).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def round_trip_set() -> list[FrozenMapping]:
    return generated_payloads(seed=3, count=500)


@pytest.mark.parametrize(("source", "expected"), VECTORS)
def test_vectors_decode(source: object, expected: bytes) -> None:
    decoded = decode_payload(expected)
    assert decoded == FrozenMapping(source)
    assert tagged(decoded) == tagged(source)
    assert decoded.canonical_bytes() == expected


def test_round_trip_generated(round_trip_set: list[FrozenMapping]) -> None:
    for p in round_trip_set:
        b = p.canonical_bytes()
        q = decode_payload(b)
        assert q == p
        assert tagged(q) == tagged(p)
        assert q.canonical_bytes() == b


def test_decoder_never_yields_float(round_trip_set: list[FrozenMapping]) -> None:
    for p in round_trip_set:
        q = decode_payload(p.canonical_bytes())
        assert not any(type(value) is float for value in reachable_values(q))


def S(x: bytes) -> bytes:
    return b'{"$map":{"a":"' + x + b'"}}'


def I(x: bytes) -> bytes:
    return b'{"$map":{"n":' + x + b"}}"


def D(x: bytes) -> bytes:
    return b'{"$map":{"d":{"$decimal":"' + x + b'"}}}'


NON_CANONICAL: dict[str, object] = {
    # structure
    "empty": b"",
    "truncated": b'{"$map":{',
    "trailing_byte": b'{"$map":{}}x',
    "trailing_newline": b'{"$map":{}}\n',
    "bom": b"\xef\xbb\xbf" + b'{"$map":{}}',
    "space_after_colon": b'{"$map": {}}',
    "space_after_brace": b'{ "$map":{}}',
    "unsorted_keys": b'{"$map":{"b":1,"a":1}}',
    "duplicate_keys": b'{"$map":{"a":1,"a":1}}',
    "untagged_object": b'{"a":1}',
    "unknown_tag": b'{"$set":{}}',
    "map_second_key": b'{"$map":{},"x":1}',
    "map_array": b'{"$map":[]}',
    "decimal_second_key": b'{"$map":{"d":{"$decimal":"1","x":1}}}',
    "decimal_not_string": b'{"$map":{"d":{"$decimal":1}}}',
    # top level not a mapping
    "top_array": b"[]",
    "top_null": b"null",
    "top_string": b'"x"',
    "top_integer": b"1",
    "top_decimal": b'{"$decimal":"1"}',
    # string escapes
    "escape_solidus": S(b"\\/"),
    "escape_u0041": S(b"\\u0041"),
    "escape_u0008": S(b"\\u0008"),
    "escape_u0009": S(b"\\u0009"),
    "escape_u000a": S(b"\\u000a"),
    "escape_u000c": S(b"\\u000c"),
    "escape_u000d": S(b"\\u000d"),
    "escape_uppercase_hex": S(b"\\u001F"),
    "escape_u007f": S(b"\\u007f"),
    "escape_u0022": S(b"\\u0022"),
    "escape_u005c": S(b"\\u005c"),
    "escape_u00e9": S(b"\\u00e9"),
    "raw_control_byte": S(b"\x01"),
    "escape_lone_surrogate": S(b"\\ud800"),
    "escape_surrogate_pair": S(b"\\ud83d\\ude00"),
    "invalid_utf8": S(b"\xff"),
    "overlong_utf8": S(b"\xc0\x80"),
    "utf8_surrogate": S(b"\xed\xa0\x80"),
    # integers
    "int_leading_zero": I(b"01"),
    "int_negative_zero": I(b"-0"),
    "int_plus": I(b"+1"),
    "int_fraction": I(b"1.5"),
    "int_exponent": I(b"1e2"),
    "int_2_53": I(b"9007199254740992"),
    "int_minus_2_53": I(b"-9007199254740992"),
    "int_5000_digits": I(b"1" * 5000),
    # decimals
    "dec_lower_e": D(b"1e2"),
    "dec_e_no_sign": D(b"1E2"),
    "dec_plus": D(b"+1"),
    "dec_leading_zero": D(b"01"),
    "dec_no_int_part": D(b".5"),
    "dec_no_fraction": D(b"1."),
    "dec_nan": D(b"NaN"),
    "dec_infinity": D(b"Infinity"),
    "dec_underscore": D(b"1_0"),
    "dec_arabic_indic_digit": D("\u0661".encode()),
    "dec_non_canonical_100": D(b"1.00E+2"),
    "dec_leading_space": D(b" 1"),
    "dec_exponent_overflow": D(b"1E+99999999999999999999"),
    "dec_exponent_underflow": D(b"1E-99999999999999999999"),
    "dec_exponent_huge": D(b"1E+1000000000000000000"),
    "dec_nul_after_digit": D(b"1\x00"),
    "dec_escaped_digit": D(b"\\u0031"),
    "dec_nbsp_before_digit": D(b"\xc2\xa01"),
    # literals
    "literal_true_capitalised": b'{"$map":{"a":True}}',
    "literal_null_uppercase": b'{"$map":{"a":NULL}}',
    # non-bytes arguments
    "arg_str": '{"$map":{}}',
    "arg_bytearray": bytearray(b'{"$map":{}}'),
    "arg_memoryview": memoryview(b'{"$map":{}}'),
}


@pytest.mark.parametrize("data", NON_CANONICAL.values(), ids=NON_CANONICAL.keys())
def test_non_canonical_bytes_are_refused(data: object) -> None:
    with pytest.raises(PayloadError):
        decode_payload(data)


def test_canonical_neighbours_are_accepted() -> None:
    """Positive companions of N6: the canonical spellings next to the refused ones decode."""
    assert decode_payload(S(b"\\u0001"))["a"] == "\x01"
    assert decode_payload(S(b"\\u001f"))["a"] == "\x1f"
    assert decode_payload(S(b'\\b\\t\\n\\f\\r\\"\\\\'))["a"] == '\b\t\n\f\r"\\'
    assert decode_payload(S(b"\x7f\xc3\xa9\xf0\x9f\x98\x80"))["a"] == "\x7f\u00e9\U0001f600"
    assert decode_payload(I(b"0"))["n"] == 0
    assert decode_payload(I(b"-9007199254740991"))["n"] == -9007199254740991
    assert tagged(decode_payload(D(b"-0"))["d"]) == ("dec", Decimal("-0").as_tuple())
    assert tagged(decode_payload(D(b"100"))["d"]) == ("dec", Decimal(100).as_tuple())


ALLOWED = frozenset({"UnicodeDecodeError", "UnicodeEncodeError", "InvalidOperation"})
NEVER_CAUGHT = frozenset(
    {
        "Exception",
        "BaseException",
        "ArithmeticError",
        "LookupError",
        "MemoryError",
        "RecursionError",
        "SystemError",
        "KeyboardInterrupt",
        "SystemExit",
        "GeneratorExit",
    }
)
PROTECTED = ALLOWED | NEVER_CAUGHT


def _handler_violation(handler: ast.ExceptHandler) -> str | None:
    where = f"line {handler.lineno}"
    if handler.type is None:
        return f"{where}: bare except"
    names = handler.type.elts if type(handler.type) is ast.Tuple else [handler.type]
    for name in names:
        if type(name) is not ast.Name:
            return f"{where}: handler class is not a bare name"
        if name.id not in ALLOWED:
            return f"{where}: handler names {name.id}"
    return None


def _is_exempt_import(node: ast.ImportFrom, alias: ast.alias) -> bool:
    return node.module == "decimal" and node.level == 0 and alias.name == "InvalidOperation" and alias.asname is None


def _bound_names(node: ast.AST) -> list[str]:
    """Names that `node` itself binds (SE-2 spec 5.6, N16)."""
    if type(node) is ast.Name and type(node.ctx) in (ast.Store, ast.Del):
        return [node.id]
    if type(node) is ast.arg:
        return [node.arg]
    if type(node) in (
        ast.ExceptHandler,
        ast.MatchAs,
        ast.MatchStar,
        ast.FunctionDef,
        ast.AsyncFunctionDef,
        ast.ClassDef,
        ast.TypeVar,
        ast.ParamSpec,
        ast.TypeVarTuple,
    ):
        name = getattr(node, "name", None)
        return [name] if name is not None else []
    if type(node) is ast.MatchMapping:
        return [node.rest] if node.rest is not None else []
    if type(node) is ast.Import:
        return [alias.asname or alias.name for alias in node.names]
    if type(node) is ast.ImportFrom:
        return [alias.asname or alias.name for alias in node.names if not _is_exempt_import(node, alias)]
    if type(node) is ast.Global or type(node) is ast.Nonlocal:
        return list(node.names)
    return []


def handler_violations(source: str) -> list[str]:
    """Violations of SE-2 spec 5.6 in `source`: a handler outside `ALLOWED`, or a binding of a protected name."""
    violations: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if type(node) is ast.ExceptHandler:
            violation = _handler_violation(node)
            if violation is not None:
                violations.append(violation)
        violations.extend(f"binding of {name}" for name in _bound_names(node) if name in PROTECTED)
    return violations


VIOLATING_SNIPPETS = [
    "try: pass\nexcept: pass",
    "try: pass\nexcept Exception: pass",
    "try: pass\nexcept decimal.InvalidOperation: pass",
    "try: pass\nexcept f(): pass",
    "try: pass\nexcept (UnicodeDecodeError, BaseException): pass",
    "E = BaseException\ntry: pass\nexcept E: pass",
    "UnicodeDecodeError = BaseException",
    "def f(InvalidOperation=BaseException): pass",
    "from builtins import BaseException as UnicodeDecodeError",
    "from builtins import BaseException as InvalidOperation",
    "import decimal as InvalidOperation",
    "for UnicodeEncodeError in (): pass",
    "try: pass\nexcept* MemoryError: pass",
    "def f[InvalidOperation](): pass",
    "class C[*UnicodeDecodeError]: pass",
    "type T[**MemoryError] = int",
]


def test_module_catches_no_process_failure() -> None:
    assert handler_violations(PAYLOAD_SOURCE) == []
    for snippet in VIOLATING_SNIPPETS:
        assert handler_violations(snippet), snippet


def test_handler_checker_accepts_the_allowed_forms() -> None:
    source = (
        "from decimal import InvalidOperation\n"
        "try: pass\nexcept InvalidOperation as exc: pass\n"
        "try: pass\nexcept (UnicodeDecodeError, UnicodeEncodeError): pass\n"
    )
    assert handler_violations(source) == []


def test_memory_error_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    def raiser(text: str) -> Decimal:
        raise MemoryError

    monkeypatch.setattr(payload, "_decimal_from_text", raiser)
    with pytest.raises(MemoryError):
        decode_payload(b'{"$map":{"d":{"$decimal":"1"}}}')


def test_tag_like_keys_round_trip() -> None:
    sources: list[dict[str, object]] = [{"$decimal": "1"}, {"$map": {}}, {"$map": {"$decimal": "1"}}]
    for source in sources:
        p = FrozenMapping(source)
        q = decode_payload(p.canonical_bytes())
        assert q == p
        assert tagged(q) == tagged(source)
    assert type(decode_payload(b'{"$map":{"$decimal":"1"}}')["$decimal"]) is str
    inner = decode_payload(b'{"$map":{"$map":{"$map":{}}}}')["$map"]
    assert type(inner) is FrozenMapping
    assert len(inner) == 0


EXPONENT_OUT_OF_RANGE = ["dec_exponent_overflow", "dec_exponent_underflow", "dec_exponent_huge"]
DECODE_CONTEXTS: dict[str, Context] = {
    "no_traps": Context(traps=[]),
    "range_traps": Context(traps=[Overflow, Underflow, Inexact, Rounded, Clamped]),
}


@pytest.mark.parametrize("ctx", DECODE_CONTEXTS.values(), ids=DECODE_CONTEXTS.keys())
@pytest.mark.parametrize("name", EXPONENT_OUT_OF_RANGE)
def test_exponent_out_of_range_is_refused_in_any_context(name: str, ctx: Context) -> None:
    with localcontext(ctx), pytest.raises(PayloadError):
        decode_payload(NON_CANONICAL[name])


@pytest.mark.parametrize("ctx", ALTERED_CONTEXTS, ids=ALTERED_CONTEXT_IDS)
def test_decoding_ignores_context(ctx: Context) -> None:
    expected = [data for _, data in VECTORS] + [p.canonical_bytes() for p in generated_payloads(seed=3, count=50)]
    trees = [tagged(decode_payload(data)) for data in expected]
    with localcontext(ctx):
        decoded = [decode_payload(data) for data in expected]
    assert [q.canonical_bytes() for q in decoded] == expected
    assert [tagged(q) for q in decoded] == trees


def test_decode_leaves_context_flags() -> None:
    with localcontext(Context(traps=[])) as ctx:
        with pytest.raises(PayloadError):
            decode_payload(D(b"x"))
        assert not ctx.flags[InvalidOperation]


@pytest.mark.parametrize(
    "value",
    [Decimal("1E+999999"), Decimal("-1E-999999"), Decimal("1" + "234567890" * 55 + "1234")],
    ids=["huge_exponent", "tiny_exponent", "long_coefficient"],
)
def test_extreme_decimal_round_trips(value: Decimal) -> None:
    p = FrozenMapping({"d": value})
    b = p.canonical_bytes()
    q = decode_payload(b)
    assert q == p
    assert tagged(q) == tagged({"d": value})
    assert q.canonical_bytes() == b
