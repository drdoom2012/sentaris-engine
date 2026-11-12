# SE-2 Payload Values and Canonical Form Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. In this project the lifecycle is `/slice SE-2` (`.claude/skills/slice/SKILL.md`); its rules override the sub-skill.

**Goal:** The engine's immutable payload type with exact A.1 validation, freezing by copy, the A.2 canonical encoder, a strict decoder and equality by canonical form.

**Architecture:** One pure module `sentaris_engine.domain.payload`. Every walk over a payload (construction, encoding, decoding, `repr`) uses an explicit work stack, never recursion (spec 5.3, U1). The decoder parses with its own parser, then re-encodes and requires identical bytes (spec 5.5).

**Tech Stack:** Python 3.12 stdlib only (`collections.abc`, `decimal`, `typing`); pytest, mypy strict, ruff, as set up in SE-1.

**Spec:** `docs/superpowers/specs/2026-11-12-se-2-payload-canonical-form-design.md` (revision 3, approved 2026-11-12). "Spec 5.1" and "N6" below refer to it; the domain document is `docs/domain.md` (Appendix A).

**Revision:** 2, after one Opus plan review (`slice-reviewer`: 1 HIGH, 11 MEDIUM, 6 LOW, all addressed; re-review: approved, 1 new LOW, addressed).

## Global Constraints

- The module imports only from the pinned pure-stdlib allowlist (`tests/architecture/purity.py`); no list in `tests/architecture/` is changed. No new dependency of any kind (no `hypothesis`, no `pytest-timeout`). Tests are under the banned-name check only, so `subprocess`, `os`, `sys`, `random`, `ast` are allowed there.
- No recursion over the payload structure anywhere in the module (spec 5.3). No `json`, no `str()`/`format()`/`repr()` of a `Decimal` in the encoder (spec 5.2, 5.4). Test helpers that walk payloads are iterative too.
- Exception handlers in the module name only `UnicodeDecodeError`, `UnicodeEncodeError` or `InvalidOperation` (imported as `from decimal import InvalidOperation`), as a bare `Name` or a tuple of bare `Name`s; nothing in the module binds those names or any name of spec 5.6's never-caught list, except that one import (spec 5.6, N16).
- Rejection tests assert the exception class `PayloadError` only, never the message.
- Tests never call `sys.setrecursionlimit`. Randomness in tests only through `random.Random(<fixed seed>)`.
- In test source, non-ASCII and control characters are written as escapes (`"\uffff"`, `"\U0001f600"`, `b"\xc0\x80"`), never as literal characters.
- Intentional type misuse in tests gets a narrow `# type: ignore[<code>]` with only the needed code (`warn_unused_ignores` is on under strict).
- Comments and docstrings cite rules by ID (`DR-10`, `A.2`, `OD-25`); they do not restate them.
- No change to `docs/domain.md` or `docs/roadmap.md`.

## Review Focus

1. **`bool` is an `int` subclass.** `True` must never pass the integer branch or encode as `1`; `type(v) is int` everywhere, never `isinstance`. Test: `test_bool_is_not_integer` in Task 2 (bytes of `{"a": True}` are `{"$map":{"a":true}}`, of `{"a": 1}` are `{"$map":{"a":1}}`).
2. **A `FrozenMapping` passed as a nested value or as the source** must not be re-walked and must keep its cached bytes valid. Test: `test_frozen_value_is_reused` in Task 1 (`inner = FrozenMapping({"x": 1}); FrozenMapping({"a": inner})["a"] is inner`).
3. **Keys that look like tags** (`"$map"`, `"$decimal"`) are ordinary keys. Test: `test_tag_like_keys_round_trip` in Task 3 (`{"$decimal": "1"}` and `{"$map": {}}` as user payloads round-trip and are not read as tags).
4. **Caller's `decimal` context after decoding malformed text** is unchanged (spec 5.5). Test: `test_decode_leaves_context_flags` in Task 3.
5. **`Decimal` with a huge exponent or many digits** (`Decimal("1E+999999")`, `Decimal("-1E-999999")`, a 500-digit coefficient) is finite and accepted (U1). Test: `test_extreme_decimal_round_trips` in Task 3.

---

## File structure

| File | Responsibility |
|---|---|
| `src/sentaris_engine/domain/payload.py` | Create (Task 1), extend (Tasks 2, 3). `PayloadError`, `MAX_INT`, `is_payload_scalar`, `FrozenMapping`, `decode_payload`, `_decimal_text`, `_decimal_from_text`. |
| `tests/domain/__init__.py` | Create, empty (tests are a package, SE-1). |
| `tests/domain/payload_helpers.py` | Task 1: iterative test helpers `tagged(value: object) -> object` and `reachable_values(p: FrozenMapping) -> list[object]`. Task 2 adds `VECTORS`, `generated_payloads`, `generated_decimals`, `decimal_class`. |
| `tests/domain/test_payload_construction.py` | Task 1. |
| `tests/domain/test_payload_encoding.py` | Task 2. |
| `tests/domain/test_payload_decoding.py` | Task 3. |
| `tests/domain/test_payload_limits.py` | Task 1 (N12 subprocess with N17 (b); N11 construction), extended in Tasks 2 and 3 (N11 remaining operations). |
| `CLAUDE.md` | Task 3: "Current state" only. |

## Interfaces (whole slice)

```python
# src/sentaris_engine/domain/payload.py
PayloadValue: TypeAlias = "None | bool | int | str | Decimal | tuple[PayloadValue, ...] | FrozenMapping"
MAX_INT: Final = 2**53 - 1

class PayloadError(ValueError): ...

def is_payload_scalar(value: object) -> bool: ...

@final
class FrozenMapping(Mapping[str, PayloadValue]):
    __slots__ = ("_items", "_bytes")   # _items: dict[str, PayloadValue], insertion order = canonical key order; _bytes: bytes | None
    def __init__(self, source: object) -> None: ...
    @classmethod
    def _from_frozen_items(cls, items: dict[str, PayloadValue]) -> "FrozenMapping": ...
    def canonical_bytes(self) -> bytes: ...          # Task 2; cached in _bytes of self only
    def __getitem__(self, key: str) -> PayloadValue: ...
    def __iter__(self) -> Iterator[str]: ...
    def __len__(self) -> int: ...
    def __eq__(self, other: object) -> bool: ...     # Task 2; NotImplemented for non-FrozenMapping
    def __hash__(self) -> int: ...                   # Task 2; hash(self.canonical_bytes())
    def __repr__(self) -> str: ...                   # Task 2; "FrozenMapping(" + canonical text + ")"

def decode_payload(data: object) -> FrozenMapping: ...   # Task 3
_decimal_from_text: Callable[[str], Decimal]              # Task 3; the only place a Decimal is built from text (spec 5.5)
```

- **`_from_frozen_items` contract (M5).** It skips validation. Its argument must hold only frozen, valid values with keys already in code-point order; it does not sort and does not check. Every caller (construction in Task 1, decoder in Task 3) sorts before calling and guarantees validity.
- `FrozenMapping(source)` with a `FrozenMapping` source returns a mapping sharing that source's `_items` and `_bytes` (no walk).
- Until Task 2, `canonical_bytes`, `__eq__`, `__hash__` and `__repr__` raise `NotImplementedError`; no Task 1 test uses `==`, `hash` or `repr` on a `FrozenMapping`, directly or through a list or tuple comparison.

Test helpers (`tests/domain/payload_helpers.py`, Task 1):

- `tagged(value)`: iterative conversion of a frozen value or a plain source value into a type-tagged tree of plain tuples: `("none",)`, `("bool", b)`, `("int", i)`, `("str", s)`, `("dec", d.as_tuple())`, `("seq", (children...))` for `list` and `tuple`, `("map", ((key, child), ...))` with keys sorted, for `dict` and `FrozenMapping`. Two trees are compared with `==`; `bool` and `int` cannot be confused, and `Decimal` compares by `as_tuple()`.
- `reachable_values(p)`: iterative list of every value reachable from `p` through `items()` and tuple elements.

---

### Task 1: Construction — validation, freezing, shared references, cycles

**Implementer model:** `opus` — the iterative depth-first walk with in-progress/finished states (spec 5.1) is the core of U1 and of the cycle/shared distinction; marking on push instead of on entry passes simple tests.

**Files:** Create `src/sentaris_engine/domain/payload.py`, `tests/domain/__init__.py`, `tests/domain/payload_helpers.py` (`tagged`, `reachable_values`), `tests/domain/test_payload_construction.py`, `tests/domain/test_payload_limits.py`.

**Interfaces:** Produces `PayloadError`, `MAX_INT`, `is_payload_scalar`, `FrozenMapping(source)` with the `Mapping` read interface, `_from_frozen_items`, the two helpers.

**Acceptance criteria:** AC-2, AC-4, AC-5, AC-12, AC-14; AC-9 for construction.

**Completion condition:** every test named below passes; `make check` exits 0; no file in `tests/architecture/` changed.

- [ ] **Step 1: Write the failing tests** in `test_payload_construction.py`:
  - `test_scalar_predicate` (N15): `is_payload_scalar(v) is True` for `True`, `False`, `0`, `MAX_INT`, `-MAX_INT`, `""`, `"\u00e9"`, `Decimal("1.0")`, `Decimal("-0")`; `is False` for `None`, `()`, `[]`, `{}`, `FrozenMapping({})`, `MAX_INT + 1`, `-MAX_INT - 1`, `1.5`, `Decimal("NaN")`, `Decimal("sNaN")`, `Decimal("Infinity")`, `Decimal("-Infinity")`, `"\ud800"`, `"a\udfff"`, `b"x"`, an `IntEnum` member, a `(str, Enum)` member, a plain `Enum` member, instances of `str`/`int`/`Decimal` subclasses, `object()`.
  - `test_rejected_value_is_refused` (N1): parametrised over the rejected values of spec N1 × the wrappers `{"v": x}`, `{"v": [x]}`, `{"v": (x,)}`, `{"v": {"w": x}}`; plus `FrozenMapping({"w": x})` itself for the nested-`FrozenMapping` position. Non-`str` keys (`1`, `True`, `None`, a `str` subclass instance) and the key `"\ud800"`, at top level and in a nested `dict`. Each `pytest.raises(PayloadError)`.
  - `test_bad_source_is_refused` (N2): `1`, `"a"`, `None`, `{1, 2}`, `(p for p in [("a", 1)])`, `[1]`, `[["a", 1]]`, `[("a",)]`, `[("a", 1, 2)]`, `[(1, "a")]`, `OrderedDict()`, `MappingProxyType({})`.
  - `test_empty_pairs_give_empty_mapping`: `len(FrozenMapping([])) == 0`, `len(FrozenMapping(())) == 0`.
  - `test_duplicate_key_from_pairs_is_refused` (N3): `[("a", 1), ("a", 2)]`; `[("a", 1), ("b", 2), ("a", 1)]`; `FrozenMapping([("k", 1), ("k", 1)])` used as a nested value raises at its own construction.
  - `test_source_mutation_does_not_change_payload` (N4): source `{"a": [1, 2], "b": "x"}` and pair source `[("a", [1])]`; after `append`, item set and `del` on the sources, `tagged(p)` equals the `tagged` of an untouched copy taken before.
  - `test_no_mutable_value_is_reachable` (N4): for a payload with every kind nested three deep, every element of `reachable_values(p)` has `type(v)` in `{type(None), bool, int, str, Decimal, tuple, FrozenMapping}`.
  - `test_mapping_cannot_be_mutated` (N4): `p["a"] = 1` and `del p["a"]` raise `TypeError`; `p.x = 1` and `del p._items` raise `AttributeError`; `not hasattr(p, "__dict__")`.
  - `test_mapping_cannot_be_subclassed` (N4): defining `class Sub(FrozenMapping): pass` inside `pytest.raises(TypeError)`.
  - `test_iteration_is_in_code_point_order` (N8, iteration part): `list(FrozenMapping({"b": 1, "a": 2, "Z": 3})) == ["Z", "a", "b"]`; same for `[("b", 1), ("Z", 3), ("a", 2)]`.
  - `test_list_becomes_tuple`: `tagged(FrozenMapping({"a": [1, [2]]})["a"]) == ("seq", (("int", 1), ("seq", (("int", 2),))))` and both levels are exactly `tuple`; `FrozenMapping({"a": [("k", 1)]})["a"]` is a `tuple` whose element is the `tuple` `("k", 1)` (spec 5.1: nested pairs are a sequence).
  - `test_frozen_value_is_reused` (Review Focus 2).
  - `test_shared_container_is_accepted` (N17): the five cases of spec N17; for each, `tagged(FrozenMapping(shared)) == tagged(FrozenMapping(copied))` where `copied` is the same structure built from separate copies; `reachable_values` passes the type check.
  - `test_shared_container_is_frozen_once` (N17 (a)): `level = [1]`, then four times `level = [level, level]`, payload `FrozenMapping({"c": level})`; walking down, at every level `t[0] is t[1]`.

  In `test_payload_limits.py`:
  - `DEPTH` is computed inside a `scope="module"` fixture `depth() -> int` as `max(10 * sys.getrecursionlimit(), 10_000)` (spec N11).
  - `test_cyclic_container_is_refused` (N12, with N17 (b)): one `subprocess.run([sys.executable, "-c", SCRIPT], timeout=20, capture_output=True, text=True)`. `SCRIPT` builds and tries, in this order: `self_list`, `self_dict`, `tuple_cycle` (`l = []; l.append((l,))`), `indirect3`, `diamond_back_edge`, `deep_cycle` (closed at `max(10 * sys.getrecursionlimit(), 10_000)`), each printing `"<name>:<exception class name or OK>"` with `flush=True`; then `chain30` last (30-level `[level, level]` chain, construction only). Assert `returncode == 0` and `stdout.splitlines() == ["self_list:PayloadError", "self_dict:PayloadError", "tuple_cycle:PayloadError", "indirect3:PayloadError", "diamond_back_edge:PayloadError", "deep_cycle:PayloadError", "chain30:OK"]`. On `subprocess.TimeoutExpired`, `pytest.fail` with the partial stdout in the message.
  - `test_no_implicit_depth_bound` (N11, construction part): parametrised over `"sequence"`, `"mapping"`, `"alternating"`; a `scope="module"` fixture builds each source iteratively to `depth` and constructs the payload once; this task asserts construction succeeds and that walking down `depth` levels reaches the leaf. Tasks 2 and 3 add assertions to this same test.

- [ ] **Step 2: Run** `uv run pytest tests/domain -q`. Expected: errors (`ModuleNotFoundError: No module named 'sentaris_engine.domain.payload'`).

- [ ] **Step 3: Implement** in `payload.py`:
  - `is_payload_scalar`: exact-type checks; surrogate check by scanning code points (`any("\ud800" <= ch <= "\udfff" for ch in s)`), so no exception is involved; `Decimal.is_finite()`.
  - `FrozenMapping.__init__`: classify the source (spec 5.1 shapes); for a pair source check each pair shape and key, reject duplicates. Then one iterative depth-first walk with an explicit stack of frames. A frame's container `id` goes into `in_progress` when the frame is **entered** (first popped), not when pushed. A child container whose `id` is in `in_progress` → `PayloadError` (cycle); in `finished` → reuse its memoised frozen value; otherwise push a frame for it. A `FrozenMapping` child is used as is. When a frame's last child is frozen: build its frozen value (`tuple`, or `_from_frozen_items` with keys sorted by the caller), remove from `in_progress`, store in `finished`. Keys checked (exact `str`, no surrogate).
  - `__init_subclass__` raises `TypeError`; `__setattr__`/`__delattr__` raise `AttributeError`; internal assignment via `object.__setattr__`.

- [ ] **Step 4: Run** `uv run pytest tests/domain -q` → all pass; `make check` → exit 0.

- [ ] **Step 5: Commit** `feat(domain): payload construction and freezing (SE-2 T1)`.

---

### Task 2: Canonical encoder, equality, hash, repr

**Implementer model:** `opus` — the canonical form is a domain contract with byte-exact vectors and context independence (CLAUDE.md "canonical form").

**Files:** Modify `payload.py` (`_decimal_text`, string encoding, `canonical_bytes`, `__eq__`, `__hash__`, `__repr__`), `tests/domain/payload_helpers.py` (add samples), `tests/domain/test_payload_limits.py` (N11 additions). Create `tests/domain/test_payload_encoding.py`.

**Interfaces:** Consumes Task 1. Produces `canonical_bytes() -> bytes`, `==`, `hash`, `repr`; in `payload_helpers.py`: `VECTORS: list[tuple[object, bytes]]` (the eight A.3 Python sources exactly as written in A.3, and their bytes copied verbatim from `docs/domain.md`), `generated_decimals(seed: int, count: int) -> list[Decimal]`, `decimal_class(d: Decimal) -> str`, `generated_payloads(seed: int, count: int) -> list[FrozenMapping]`.

**Acceptance criteria:** AC-1 (encode direction), AC-3, AC-6, AC-10, AC-11; AC-9 for encoding, equality, hash, `repr`.

**Completion condition:** every test named below passes; `make check` exits 0; no file in `tests/architecture/` changed.

- [ ] **Step 1: Write the generators** in `payload_helpers.py`:
  - `decimal_class(d)` returns one of `"e0"`, `"plain"` (`e < 0`, `a >= -6`, `-e < n`), `"leading_zeros"` (`e < 0`, `a >= -6`, `-e >= n`), `"sci_small"` (`a < -6`), `"sci_positive"` (`e > 0`), with the spec 5.4 definitions of `e`, `n`, `a`.
  - `generated_decimals(seed, count)`: `random.Random(seed)`; sign random; coefficient 1–25 digits (or the single digit `0` with probability 0.1); exponent uniform in −30..30. Built with `Decimal((sign, digits, exp))`.
  - `generated_payloads(seed, count)`: depth ≤ 4, at most 5 entries per container; leaves drawn from: `None`, `True`, `False`, integers including `0`, `±MAX_INT`, small negatives; strings drawn from a pool containing every A.2 escape class (each control code point, `"`, `\`), U+007F, `"\u00e9"`, `"\U0001f600"`; decimals from `generated_decimals` plus `Decimal("-0")`; keys from a pool including `"$map"`, `"$decimal"`, `"\u00e9"`, `"\U0001f600"`, `""`, a proper prefix pair `"a"`/`"ab"`; `dict` sources built with keys inserted in random order; sequences as `list` or `tuple` at random.

- [ ] **Step 2: Write the failing tests** in `test_payload_encoding.py`:
  - `test_vectors_encode` (AC-1): `FrozenMapping(source).canonical_bytes() == expected` for each of `VECTORS`.
  - `test_bool_is_not_integer` (Review Focus 1).
  - `test_decimal_text_matches_default_str` (N7): values = the A.3 decimals, the spec 5.4 examples (`100`, `1.00E+2`, `0.0005`, `0E-3`, `1E+2`, `0E+3`, `0.0000001`, `-0`), the boundary values `Decimal("0.000001")` → `0.000001`, `Decimal("0.000001234")` → `0.000001234`, `Decimal("12E-8")` → `1.2E-7` (asserted as literal texts), and `generated_decimals(seed=2, count=1000)`. Under `decimal.localcontext(decimal.Context())`, the `$decimal` text in the bytes of `FrozenMapping({"d": d})` equals `str(d)`. Also assert `{decimal_class(d) for d in generated}` equals all five classes, and that the generated set contains a zero coefficient with positive exponent, one with negative exponent, and a negative zero.
  - `test_decimal_text_ignores_context` (N7, DR-13): contexts in this order: `Context(capitals=0)`, `Context(prec=1)`, `Context(rounding=ROUND_DOWN)`, `Context(Emax=10, Emin=-10)`, `Context(traps=[])`. For the A.3 decimal vectors and `generated_decimals(seed=2, count=1000)`, both construction and encoding happen inside `localcontext(ctx)`, and the bytes equal those under the default context.
  - `test_string_escaping` (N13): for each code point 0x00–0x1F, `"`, `\`, U+007F, `"\u00e9"`, `"\U0001f600"`, as value and as key, against expected bytes built from the A.2 table (short escapes for 0x08, 0x09, 0x0A, 0x0C, 0x0D; `\u00xx` lowercase otherwise; literal UTF-8 for the rest). Plus literal expectations written out: `{"a": "\x1f"}` → `b'{"$map":{"a":"\\u001f"}}'`; `{"a": "\x08"}` → `b'{"$map":{"a":"\\b"}}'`; `{"a": "\x7f"}` → `b'{"$map":{"a":"\x7f"}}'`; `{"a": "\U0001f600"}` → `b'{"$map":{"a":"\xf0\x9f\x98\x80"}}'`.
  - `test_key_order_is_by_code_point` (N14): keys `"b"`, `"ab"`, `"a"`, `"Z"`, `"\uffff"`, `"\U0001f600"` → iteration and bytes in the order `Z, a, ab, b, \uffff, \U0001f600`.
  - `test_construction_order_does_not_change_form_or_iteration` (N8): all `itertools.permutations` of 4 entries, as `dict` and as pairs → identical bytes and iteration.
  - `test_equality_is_by_canonical_form` (N5): `{"a": True}` vs `{"a": 1}` unequal; `Decimal("1.0")`, `Decimal("1.00")`, `Decimal("1E+1")` pairwise unequal; `Decimal("0")` vs `Decimal("-0")` unequal; `"1"`, `1`, `True`, `Decimal("1")`, `None` under key `"v"` pairwise unequal; `{"s": [1, 2]}` equals `{"s": (1, 2)}`; `(FrozenMapping({}) == {}) is False`.
  - `test_hash_follows_equality` (N5): the equal pairs above hash equal.
  - `test_shared_container_is_accepted_bytes` (N17): the five N17 cases, shared `==` copied.
  - `test_repr_shows_canonical_form`: `repr(FrozenMapping({"a": 1})) == 'FrozenMapping({"$map":{"a":1}})'`.
  - `test_canonical_form_is_identical_across_processes` (N10): `REPO_ROOT = Path(__file__).resolve().parents[2]`; two `subprocess.run([sys.executable, "-c", SCRIPT], cwd=REPO_ROOT, env={**os.environ, "PYTHONHASHSEED": seed}, ...)` with seeds `"0"` and `"1"`; `SCRIPT` imports `tests.domain.payload_helpers` and prints the hex of the bytes of each of `VECTORS` and `generated_payloads(seed=1, count=50)`; both outputs identical and equal to the same list computed in process.
  - In `test_payload_limits.py`, extend `test_no_implicit_depth_bound`: `b = p.canonical_bytes()` succeeds; `p == p_copy` and `hash(p) == hash(p_copy)` for a second payload built from the same source; `repr(p).startswith("FrozenMapping(")`.

- [ ] **Step 3: Run** `uv run pytest tests/domain -q` → the new tests fail with `NotImplementedError`.

- [ ] **Step 4: Implement.** `_decimal_text(d: Decimal) -> str` from `d.as_tuple()` exactly per spec 5.4. String encoding per A.2's escape table. `canonical_bytes`: one iterative pass with an explicit stack producing a list of `str` pieces, then `"".join(pieces).encode("utf-8")`; keys in stored order; cache in `self._bytes` only (never on nested mappings, spec 5.3). `__eq__`: `NotImplemented` unless `type(other) is FrozenMapping`, else bytes equality. `__hash__`: `hash(self.canonical_bytes())`.

- [ ] **Step 5: Run** `uv run pytest tests/domain -q` → pass; `make check` → exit 0.

- [ ] **Step 6: Commit** `feat(domain): canonical encoder and equality by canonical form (SE-2 T2)`.

---

### Task 3: Strict decoder, exception handling, documentation

**Implementer model:** `opus` — strictness against non-canonical input and the exception policy of spec 5.6 are both subtle; N6 is the longest negative list of the slice.

**Files:** Modify `payload.py` (`decode_payload`, `_decimal_from_text`), `tests/domain/test_payload_limits.py` (N11 additions), `CLAUDE.md` ("Current state" only). Create `tests/domain/test_payload_decoding.py`.

**Interfaces:** Consumes Tasks 1–2. Produces `decode_payload(data: object) -> FrozenMapping` and the module-level `_decimal_from_text`.

**Acceptance criteria:** AC-1 (decode direction), AC-7, AC-8, AC-13, AC-15; AC-9 for decoding and round trip.

**Completion condition:** every test named below passes; `make check` exits 0; no file in `tests/architecture/` changed; `uv run pytest tests/domain -q --durations=15` run and its total time reported.

- [ ] **Step 1: Write the failing tests** in `test_payload_decoding.py`:
  - `test_vectors_decode` (AC-1): for each of `VECTORS`, `decode_payload(expected) == FrozenMapping(source)` and `decode_payload(expected).canonical_bytes() == expected`.
  - `test_round_trip_generated` (AC-8): `generated_payloads(seed=3, count=500)`; decode of each payload's bytes equals it and re-encodes to identical bytes.
  - `test_decoder_never_yields_float` (N9): `reachable_values` of every decoded payload of the round-trip set contains no `float`.
  - `test_non_canonical_bytes_are_refused` (N6), parametrised over exactly these inputs (each `pytest.raises(PayloadError)`; any other exception fails):
    - structure: `b""`; `b'{"$map":{'`; `b'{"$map":{}}x'`; `b'{"$map":{}}\n'`; `b"\xef\xbb\xbf" + b'{"$map":{}}'`; `b'{"$map": {}}'`; `b'{ "$map":{}}'`; `b'{"$map":{"b":1,"a":1}}'`; `b'{"$map":{"a":1,"a":1}}'`; `b'{"a":1}'`; `b'{"$set":{}}'`; `b'{"$map":{},"x":1}'`; `b'{"$map":[]}'`; `b'{"$map":{"d":{"$decimal":"1","x":1}}}'`; `b'{"$map":{"d":{"$decimal":1}}}'`;
    - top level not a mapping: `b"[]"`, `b"null"`, `b'"x"'`, `b"1"`, `b'{"$decimal":"1"}'`;
    - string escapes (with `S(x) = b'{"$map":{"a":"' + x + b'"}}'`): `S(b"\\/")`; `S(b"\\u0041")`; `S(b"\\u0008")`, `S(b"\\u0009")`, `S(b"\\u000a")`, `S(b"\\u000c")`, `S(b"\\u000d")`; `S(b"\\u001F")`; `S(b"\\u007f")`; `S(b"\\u0022")`; `S(b"\\u005c")`; `S(b"\\u00e9")`; `S(b"\x01")` (raw control byte); `S(b"\\ud800")`; `S(b"\\ud83d\\ude00")`; `S(b"\xff")` (invalid UTF-8); `S(b"\xc0\x80")` (overlong); `S(b"\xed\xa0\x80")` (encoded surrogate);
    - integers (with `I(x) = b'{"$map":{"n":' + x + b'}}'`): `I(b"01")`, `I(b"-0")`, `I(b"+1")`, `I(b"1.5")`, `I(b"1e2")`, `I(b"9007199254740992")`, `I(b"-9007199254740992")`, `I(b"1" * 5000)`;
    - decimals (with `D(x) = b'{"$map":{"d":{"$decimal":"' + x + b'"}}}'`): `D(b"1e2")`, `D(b"1E2")`, `D(b"+1")`, `D(b"01")`, `D(b".5")`, `D(b"1.")`, `D(b"NaN")`, `D(b"Infinity")`, `D(b"1_0")`, `D("\u0661".encode())` (Arabic-Indic digit one), `D(b"1.00E+2")`, `D(b" 1")`;
    - literals: `b'{"$map":{"a":True}}'`, `b'{"$map":{"a":NULL}}'`;
    - non-`bytes` arguments: `'{"$map":{}}'`, `bytearray(b'{"$map":{}}')`, `memoryview(b'{"$map":{}}')`.
  - `test_module_catches_no_process_failure` (N16): a checker function `handler_violations(source: str) -> list[str]` parses the source with `ast`, then:
    - every `ExceptHandler` (in `Try` and `TryStar`): `type` is not `None`, and is a `Name` or a `Tuple` of `Name`s whose ids are all in `ALLOWED = {"UnicodeDecodeError", "UnicodeEncodeError", "InvalidOperation"}`; anything else is a violation;
    - no binding of a name in `ALLOWED | NEVER_CAUGHT` (`NEVER_CAUGHT` = the ten classes of spec 5.6), collected from: every `ast.Name` with `Store` or `Del` context (covers assignment, augmented and annotated assignment, `for`, `with`, walrus, comprehension targets, `del`), every `ast.arg.arg` (all parameter kinds, lambdas included), `ExceptHandler.name`, `MatchAs.name`, `MatchStar.name`, `MatchMapping.rest`, `Import`/`ImportFrom` aliases (`asname or name`), `FunctionDef`/`AsyncFunctionDef`/`ClassDef` names, `Global`/`Nonlocal` names; the one exception is an `ImportFrom` node with `module == "decimal"`, `level == 0` and an alias with `name == "InvalidOperation"` and `asname is None`; no other binding of `InvalidOperation` is exempt.
    The test asserts `handler_violations(<payload.py source>) == []`, and that each of these snippets gives at least one violation: `try: pass\nexcept: pass`; `try: pass\nexcept Exception: pass`; `try: pass\nexcept decimal.InvalidOperation: pass`; `try: pass\nexcept f(): pass`; `try: pass\nexcept (UnicodeDecodeError, BaseException): pass`; `E = BaseException\ntry: pass\nexcept E: pass`; `UnicodeDecodeError = BaseException`; `def f(InvalidOperation=BaseException): pass`; `from builtins import BaseException as UnicodeDecodeError`; `from builtins import BaseException as InvalidOperation`; `import decimal as InvalidOperation`; `for UnicodeEncodeError in (): pass`; `try: pass\nexcept* MemoryError: pass`.
  - `test_memory_error_propagates` (N16): `monkeypatch.setattr(payload, "_decimal_from_text", raiser)` with `raiser` raising `MemoryError`; `pytest.raises(MemoryError)` around `decode_payload(b'{"$map":{"d":{"$decimal":"1"}}}')`.
  - `test_tag_like_keys_round_trip`, `test_decode_leaves_context_flags` (under `localcontext(Context(traps=[])) as ctx`, decoding `D(b"x")` raises `PayloadError` and afterwards `not ctx.flags[InvalidOperation]`), `test_extreme_decimal_round_trips` (Review Focus 3–5).
  - In `test_payload_limits.py`, extend `test_no_implicit_depth_bound`: `q = decode_payload(b)`; `q == p`; `q.canonical_bytes() == b`.

- [ ] **Step 2: Run** `uv run pytest tests/domain -q` → the new tests fail (`ImportError: cannot import name 'decode_payload'`).

- [ ] **Step 3: Implement** `decode_payload`:
  - `type(data) is not bytes` → `PayloadError`. `data.decode("utf-8")` with only `UnicodeDecodeError` translated (`raise PayloadError(...) from exc`).
  - Index-based parser with an explicit stack and explicit bounds checks (spec 5.6; no reliance on `IndexError`). Tokens accepted: `{"$map":{` entries `}}`, `{"$decimal":"` text `"}`, arrays, strings, integers, `true`, `false`, `null`.
  - **String parser (M5):** accepts a raw character only if its code point is ≥ U+0020 and it is not `"` or `\`; accepts only the escapes `\"`, `\\`, `\b`, `\t`, `\n`, `\f`, `\r`, and `\u00` followed by two lowercase hex digits giving a code point U+0000–U+001F other than the five with short forms; every other escape is rejected. So no surrogate code point can be produced.
  - Integers: shape (optional `-`, no leading zero, ASCII digits) and ≤ 16 digits before `int()`, then the ±`MAX_INT` range.
  - Decimals: text through `_decimal_from_text` inside `decimal.localcontext()`; `InvalidOperation` translated; `not d.is_finite()` rejected.
  - Nested values built bottom-up into `tuple`, and into `_from_frozen_items` with keys **sorted by the decoder** (the re-encoding below rejects unsorted input because the sorted re-encoding differs).
  - Finally `result.canonical_bytes() == data`, else `PayloadError`.

- [ ] **Step 4: Update `CLAUDE.md` "Current state":** SE-1 and SE-2 exist; SE-2 is the payload type and canonical form (`sentaris_engine.domain.payload`). No other section changes.

- [ ] **Step 5: Run** `uv run pytest tests/domain -q --durations=15` → pass, note total time; `make check` → exit 0.

- [ ] **Step 6: Commit** `feat(domain): strict canonical decoder (SE-2 T3)`.

---

## Slice completion (orchestrator, not a task)

1. `make check` on the final head; read the summary lines.
2. Budget (spec 8.1): time `uv run pytest tests/domain -q`; the SE-2 tests add at most 5 s, else the slice is not accepted until cost is reduced without loss of coverage.
3. Whole-slice review by `slice-reviewer`, fix wave, scoped re-review, `make check` again.
4. `docs/superpowers/reports/se-2.md` per the slice skill.

## Coverage of the spec

| Spec | AC | Task |
|---|---|---|
| 5.1 types, shapes, freezing, shared/cycle; N1–N4, N12, N15, N17 | AC-2, AC-4, AC-5, AC-12, AC-14 | 1 (N17 bytes equality in 2) |
| 5.2 encoder, `==`, hash, `repr`; 5.4; N5, N7, N8, N10, N13, N14 | AC-1 (encode), AC-3, AC-6, AC-10, AC-11 | 2 (N8 iteration part in 1) |
| 5.5, 5.6; N6, N9, N16 | AC-1 (decode), AC-7, AC-8, AC-15 | 3 |
| 5.3 / U1; N11 | AC-9 | 1 (construction), 2 (bytes, `==`, hash, `repr`), 3 (decode, round trip) |
| 8.1 budget | AC-13 (time) | 3 (measured), slice completion |
| Scope item 3 (`CLAUDE.md`) | — | 3 |
| Purity of the module | AC-13 | every task (`make check`, real-tree check) |
