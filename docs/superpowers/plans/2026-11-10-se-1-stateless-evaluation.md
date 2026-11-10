# SE-1 Stateless Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evaluate one stateless strategy on one hand-built evaluation context and return exactly one of signals, no signal or evaluation failure, with signal payloads that have one exactly specified canonical byte form.

**Architecture:** Pure types and rules in `domain` (time checks, payload with canonical encoder and strict decoder, parameters, candle and snapshot, signal, result, evaluation context, the stateless strategy `Protocol`). One function in `application` evaluates a strategy and refuses a result that is not one of the three outcomes. Probe strategies live in `tests/support/` and carry no market logic.

**Tech Stack:** Python 3.12 standard library only (`dataclasses`, `decimal`, `collections.abc`, `typing`), pytest, ruff, mypy strict, import-linter. No new dependency, no new import-linter allowlist entry.

**Spec:** `docs/superpowers/specs/2026-11-09-engine-roadmap-design.md` (SE-1), `docs/adr/0001-evaluation-types-and-strategy-contract.md` (normative for payloads, results, strategy contract), `docs/domain.md` revision 8 (DR-08 to DR-11, DR-13, DR-14, DR-23, DR-26). Quasar candle fields: `../quasar-market-data/docs/contracts/api-v1.md` section 1 (Decimals) and section 5.2.

## Global Constraints

- Layers: `application → strategies | infrastructure → domain`; SE-1 code is in `domain` and `application` only. `strategies` and `infrastructure` stay empty.
- `domain` imports only allowlisted modules (`dataclasses`, `decimal`, `enum`, `collections` including `collections.abc`, `types`, `typing`, `abc`, `functools`, `itertools`, `__future__`). The encoder and decoder are hand-written: do **not** import `json`, `re` or `sys`, and do not add to the allowlist. If an import fails `make imports`, stop and ask; never widen the contract.
- No wall-clock read, randomness or I/O in `domain` (DR-08). No runtime dependency.
- Time: instants (`as_of`, `open_time_ms`) are exact `int` UTC milliseconds; durations exact `int` milliseconds (OD-10).
- Payload value kinds are matched by **exact type** (`type(x) is int`, never `isinstance`): null `None`; `bool`; `int` within −(2^53 − 1) to 2^53 − 1; `str` without surrogate code points; finite `Decimal` (NaN, sNaN, Infinity and −Infinity rejected); sequence = exactly `tuple` or `list`; mapping = exactly `dict` or `Payload`; mapping keys exactly `str`. Everything else (subclasses of any accepted type, `namedtuple`, `OrderedDict`, `defaultdict`, `MappingProxyType`, enums, `set`, `frozenset`, iterators, generators, `range`, `float`, `bytes`, `bytearray`, other classes) is rejected. Containers are copied into frozen form; duplicate keys are rejected (ADR-0001).
- **No depth bound** (ADR-0001, confirmed by the user 2026-11-10): freezing, encoding and decoding are **iterative** (explicit stack), so no nesting depth raises `RecursionError`. Nested `Payload` objects do not cache bytes (that would be quadratic in depth); only the object on which `canonical()` is called caches its own bytes, lazily.
- Canonical form: ADR-0001 table, byte for byte; `Decimal` text is the to-scientific-string of sign, coefficient digits and exponent with uppercase `E`, computed from `as_tuple()`, never from `str()`, so it ignores the `decimal` context.
- Payload equality is equality of canonical bytes, never Python equality of raw values (`True == 1` and `Decimal("1.0") == Decimal("1.00")` hold in Python).
- Parameters: flat immutable mapping from `str` to scalars (`str`, `int`, `Decimal`, `bool`); null, sequence and mapping values are a construction precondition violation (my call), while a value that is merely wrong for a particular strategy is that strategy's `EvaluationFailure` (OD-13).
- Result: exactly one of `Signals` (non-empty ordered tuple), `NoSignal`, `EvaluationFailure` (non-empty string code). No engine type enumerates a signal kind (DR-23).
- ruff line length 120; mypy strict over `src` and `tests` with `warn_unused_ignores`; annotate everything. Negative tests that pass a deliberately wrong type go through `cast(Any, value)` (not bare `# type: ignore`). Builders in `tests/support/vectors.py` are typed `Callable[[], Any]`. `make check` must pass at the end of every task. Never weaken a check, contract or test.
- ruff's FURB157 (run by `make format`) rewrites `Decimal("0")` and `Decimal("1")` to `Decimal(0)` and `Decimal(1)`; the values are identical. Never write `Decimal(-0)` (it is `Decimal("0")`); negative zero is `Decimal("-0")`.
- `isinstance(x, Result)` fails at run time for a `type` alias; check results with `type(x) in (Signals, NoSignal, EvaluationFailure)`.
- **Docs in the same commit** (CLAUDE.md, `docs/domain.md` sections 9 and 11): each task's commit carries the `docs/domain.md` change that task makes true; the `docs/domain.md` revision 9 row is added in Task 1 and extended by later tasks.
- Commits: one per task, only after the user has agreed that this slice may be committed; each message ends with the executing session's attribution line. Work on a new branch `se-1-stateless-evaluation` created from `foundation` (my call).

## Review Focus

Input classes the spec implies but does not test; each has a named test in the task that owns the code.

1. **Empty history** (no candles in a series, no series in a snapshot): valid input, never an exception, never "no signal"; a strategy decides to fail. Tests: Task 5 `test_empty_series_and_empty_snapshot_are_valid`, Task 7 `test_probe_fails_when_series_is_missing`.
2. **Two candles with the same open time**: rejected, never merged or "last wins" (DR-15). Test: Task 5 `test_series_rejects_duplicate_open_time`.
3. **A price that is `float`, `int`, `str` or NaN; a `bool` used as a timestamp; a `null` turnover** (valid in Quasar, so it must be representable and is never defaulted, DR-15). Tests: Task 4 `test_instant_rejects_bool`, Task 5 `test_candle_rejects_non_decimal_and_non_finite_values`, `test_candle_accepts_null_turnover_only`.
4. **A strategy that returns `None` or a plain `dict`, or raises**: a contract error or the original exception, never "no signal" (DR-14). Tests: Task 7 `test_non_result_is_contract_error`, `test_strategy_exception_is_not_swallowed`.
5. **Payload nested far beyond the interpreter's recursion limit**: must construct, encode, decode and compare without `RecursionError`. Tests: Task 1 `test_deep_nesting_beyond_recursion_limit`, Task 2 `test_deep_nesting_decodes_beyond_recursion_limit`.

---

### Task 1: Payload construction and canonical encoder

**Files:**
- Create: `src/sentaris_engine/domain/payload.py`
- Create: `tests/__init__.py`, `tests/domain/__init__.py`, `tests/application/__init__.py`, `tests/support/__init__.py`
- Create: `tests/support/vectors.py`, `tests/domain/test_payload.py`
- Modify: `docs/domain.md` (section 2 "Built", section 9, revision 9)

**Interfaces:**
- Consumes: nothing.
- Produces (`sentaris_engine.domain.payload`):
  - `MAX_SAFE_INT: int` (`2**53 - 1`); `class PayloadError(ValueError)`
  - `type PayloadValue = None | bool | int | str | Decimal | tuple[PayloadValue, ...] | Payload`
  - `class Payload(Mapping[str, PayloadValue])`, constructed only through `Payload.of(source: dict[str, object] | Payload | Sequence[tuple[str, object]] = ()) -> Payload`. The **top level** accepts exactly: a `dict` with `str` keys, a `Payload`, or an exact `list`/`tuple` of exact 2-tuples with exact `str` first elements (pairs); anything else (a string, `["ab"]`, a generator of pairs, `OrderedDict`, `MappingProxyType`, `None`) raises `PayloadError`. Pairs exist only at the top level: a nested `[("a", 1)]` is an ordinary sequence whose element is a sequence (a `tuple` passes the kind table), never a mapping.
  - `Payload.canonical(self) -> bytes` (lazy cache); `__eq__`/`__hash__` by canonical bytes; `__iter__` in code-point key order; no mutators; `Payload(...)` called directly raises `TypeError`; `__setattr__` and `__delattr__` raise `AttributeError`; `__reduce__` returns `(Payload.from_canonical, (self.canonical(),))` so `copy`, `deepcopy` and `pickle` work without recursion (`from_canonical` is added in Task 2; until then the reduce test is skipped with `pytest.importorskip`-style guard removed in Task 2).
- `tests/support/vectors.py` produces: `VECTORS: list[tuple[str, Callable[[], Any], bytes]]` (id without whitespace, builder of the top-level source, expected canonical bytes), `REJECTED: list[tuple[str, Callable[[], Any]]]`, `CORPUS: list[tuple[str, Callable[[], Any]]]`. Builders are callables so every process builds its own values under its own `decimal` context. The module imports nothing from `tests.*` (a child process cannot import `tests`).

- [ ] **Step 1: Create the test package markers and `tests/support/vectors.py`.** Empty `__init__.py` files; run `make typecheck` and `make test` to confirm `tests/test_package.py` still passes with `tests/__init__.py` present. `VECTORS` holds the eight ADR-0001 test-vector rows with exact bytes (including the added rows for `±(2^53 − 1)` and `Decimal("-1.50E-12")` with `(True, False)`). `REJECTED` holds every "Rejected at construction" entry of ADR-0001 and: `bytes`, `bytearray`, `float`, `Decimal("Infinity")`, `Decimal("-Infinity")`, `Decimal("NaN")`, `Decimal("-NaN")`, `Decimal("sNaN")`; subclasses of `str`, `int`, `Decimal`, `tuple` (a `namedtuple`), `list` and `dict` (`OrderedDict`, `defaultdict`) used as values; `MappingProxyType` as value; `set`, `frozenset`, a generator, `iter([])`, `range(1)` as values; `object()` and a dataclass instance as values; a surrogate string as value and as key; a non-string key; nested `{"a": {"b": 2**53}}`; top-level `None`, `"ab"`, `["ab"]`, `[("a", 1, 2)]`, `[["a", 1]]`, a generator of pairs, `OrderedDict`, `MappingProxyType`. `[]` and `()` are **valid** top-level sources (empty pairs). `CORPUS` holds the vectors' sources plus: non-ASCII, an NFC/NFD pair written with `\u` escapes in the Python source (the pair for "é"), all control characters U+0000–U+001F and U+007F, `Decimal("9" * 60)`, `Decimal("1E+999999")`, `Decimal("1E-999999")`, a 500-element sequence, a mapping with 200 keys inserted in the order of a fixed permutation (`random.Random(0)`, never the global generator), a nest of depth 50.
- [ ] **Step 2: Write `tests/domain/test_payload.py`** (all fail first):
  - `test_vectors_encode_to_exact_bytes` (over `VECTORS`): `Payload.of(build()).canonical() == expected`.
  - `test_rejected_sources_raise_payload_error` (over `REJECTED`).
  - `test_empty_pair_sources_are_valid`: `Payload.of([])`, `Payload.of(())` and `Payload.of()` have bytes `{"$map":{}}`.
  - `test_integer_range_boundaries`: `±(2**53 - 1)` accepted; `±2**53` rejected; `True` stays `true` and `1` stays `1` in bytes.
  - `test_distinct_kinds_have_distinct_canonical_forms`: the values `"1"`, `1`, `True`, `Decimal("1")`, `None` under key `"v"` give five different byte strings.
  - `test_decimal_exponent_is_identity`: `Decimal("1.0")` vs `Decimal("1.00")` and `Decimal("0")` vs `Decimal("-0")` give unequal payloads with different bytes.
  - `test_null_differs_from_absent_key`.
  - `test_key_order_does_not_matter`: the same mapping from different insertion orders and from pairs gives equal payloads, equal hashes, identical bytes; `list(payload)` is in code-point order.
  - `test_equality_is_canonical_not_python`: `{"a": 1}` ≠ `{"a": True}`; `{"a": (Decimal("1.0"),)}` ≠ `{"a": (Decimal("1.00"),)}`.
  - `test_nfc_and_nfd_strings_are_distinct`: the two forms of "é" give different bytes, both literal UTF-8.
  - `test_duplicate_pair_key_is_rejected`: `Payload.of([("a", 1), ("a", 2)])`.
  - `test_nested_pairs_stay_a_sequence`: `Payload.of({"s": [("a", 1)]})` encodes as `{"$map":{"s":[["a",1]]}}` with ASCII quotes (a sequence of a sequence), never a mapping.
  - `test_mutable_inputs_are_copied`: build from a `list` and `dict` (nested), mutate the originals afterwards; bytes unchanged.
  - `test_payload_cannot_be_mutated`: through `cast(Any, …)`: item assignment on the payload, on a nested payload and on a nested sequence raises `TypeError`; assigning an **existing** slot (`p._items = 1` or the name the implementation uses) and `del` of it raise `AttributeError`; `Payload({})` raises `TypeError`; a sequence given as `list` is stored as `tuple`.
  - `test_copy_and_pickle_round_trip`: `copy.copy`, `copy.deepcopy` and `pickle.loads(pickle.dumps(p))` equal `p` (enabled once Task 2 provides `from_canonical`; write it now, mark `xfail(strict=True)`, remove the marker in Task 2).
  - `test_decimal_text_ignores_the_decimal_context`: under `decimal.localcontext()` with `capitals=0`, `prec=2`, `rounding=ROUND_DOWN` and all traps enabled, `Decimal("1E+2")` and `Decimal("64210.50")` encode to the vector bytes.
  - `test_decimal_text_equals_str_under_default_context`: for `"0"`, `"-0"`, `"-0.00"`, `"0E+2"`, `"0E-7"`, `"0.000001"`, `"0.0000001"`, `"123456789E+5"`, `"1.50E-12"`, `"1E+2"`, `"-1E-7"`, `"12345678901234567890.123"`, `"1E+999999"`, the text inside `{"$decimal":"…"}` equals `str(value)`.
  - `test_deep_nesting_beyond_recursion_limit`: a chain nested `5 * sys.getrecursionlimit()` deep (sequences and mappings alternating, built with a loop) constructs, `canonical()` returns, `==` and `hash` work, with no `RecursionError`.
- [ ] **Step 3: Run** `uv run pytest tests/domain/test_payload.py -v`. Expected: FAIL (`payload` module missing).
- [ ] **Step 4: Implement `payload.py`.** Items are stored as a plain private `tuple` of `(key, value)` pairs in code-point key order (a lookup `dict` built from it is fine; do not use `MappingProxyType`). Freezing is one iterative walk with an explicit stack that applies the exact-type table, copies `list` to `tuple` and `dict` to `Payload`, rejects duplicate keys, surrogates (by `str.encode("utf-8")` failing), out-of-range integers and everything else with `PayloadError`. The encoder is one iterative walk producing a list of byte chunks following the ADR-0001 table. `_decimal_text(value: Decimal) -> str` from `as_tuple()`: `adjusted = exponent + len(digits) - 1`; plain notation when `exponent <= 0 and adjusted >= -6` (exponent 0: the digits; more digits than `-exponent`: insert the point; otherwise `"0."`, then `-exponent - len(digits)` zeros, then the digits), else scientific: first digit, `.` and the rest if there are more digits, `E`, `+` or `-`, `abs(adjusted)`; a leading `-` when the sign bit is set (reviewer-verified against `str(Decimal)` on 200 000 random values).
- [ ] **Step 5: Run** `uv run pytest tests/domain/test_payload.py -v`, then `make check`. Expected: PASS and all four checks green (including `make imports`).
- [ ] **Step 6: Docs.** `docs/domain.md`: section 2 "Built" gains the canonical payload form; section 9: DR-11 stays `PLANNED (SE-4)` with the note that payloads reject `float` and non-finite `Decimal` (evidence `tests/domain/test_payload.py::test_rejected_sources_raise_payload_error`) because the Quasar client does not exist yet (my call; not `ENFORCED` for the whole rule); add the revision 9 row.
- [ ] **Step 7: Commit** `feat(domain): payload with canonical form`.

### Task 2: Strict decoder and round trips

**Files:**
- Modify: `src/sentaris_engine/domain/payload.py`, `tests/domain/test_payload.py` (remove the `xfail`)
- Create: `tests/domain/test_payload_decoding.py`

**Interfaces:**
- Consumes: Task 1 (`Payload`, `PayloadError`, `VECTORS`, `CORPUS`).
- Produces: `Payload.from_canonical(cls, data: bytes) -> Payload`; raises `PayloadError` for anything that is not the canonical form of some payload; never raises another exception type.

- [ ] **Step 1: Write `tests/domain/test_payload_decoding.py`:**
  - `test_round_trip_bytes` (over `VECTORS` and `CORPUS`): `Payload.from_canonical(b).canonical() == b`.
  - `test_round_trip_value_keeps_every_kind`: for each source, `Payload.from_canonical(p.canonical()) == p`, and a test helper `shape(value)` (nested tuples of `(type name, value, Decimal.as_tuple())`) is equal for both, so `bool` is not `int`, `Decimal` is not `str`, `Decimal("1.0")` keeps its exponent, null is not an absent key, sequence order is kept.
  - `test_decoder_rejects_non_canonical_input` (parametrized, one id per case, each `PayloadError`, inputs written as Python `bytes` literals): leading space; trailing space; trailing newline; BOM prefix; space after the colon; unsorted keys; duplicate keys; the escape of U+001B with an uppercase hex digit; an unnecessary escape of a printable character (in the literal: a doubled backslash, then `u0041`, inside a string value); `\/`; an escaped surrogate pair (doubled backslash, `ud83d`, doubled backslash, `ude00`) and a lone escaped surrogate (`ud800`); a `Decimal` as JSON number `{"$map":{"d":1.5}}`; `{"$decimal":"1.0E+1"}`; `{"$decimal":"1e+1"}`; `{"$decimal":"01"}`; `{"$decimal":"+1"}`; `{"$decimal":"1_0"}`; `{"$decimal":" 1"}`; `{"$decimal":"abc"}`; `{"$decimal":"NaN"}`; `{"$decimal":"1E+999999999999999999999"}`; integers `01`, `-0`, `9007199254740992`, `-9007199254740992`, a 17-digit integer, an integer written with Arabic-Indic digits and one with a superscript two; invalid UTF-8 `b"\xff"`; a tag object with an unknown key `{"$map":{"a":{"$other":"1"}}}`; a tag object with an extra key `{"$decimal":"1","x":1}`; top level `null`, `[]`, `{"$decimal":"1"}`; empty input; truncated input; `NaN`; `Infinity`; `1.5`; `1e5`.
  - `test_deep_nesting_decodes_beyond_recursion_limit`: the Task 1 deep chain round-trips bytes with no `RecursionError`.
- [ ] **Step 2: Run** `uv run pytest tests/domain/test_payload_decoding.py -v`. Expected: FAIL (`from_canonical` missing).
- [ ] **Step 3: Implement `Payload.from_canonical`** as a hand-written **iterative** parser over the strictly UTF-8-decoded text that accepts only the shapes the encoder produces (`null`, `true`, `false`, `-?digits`, strings with escapes for quote, backslash, `b t n f r` and `u` plus four hex digits, arrays, `{"$decimal":"…"}`, `{"$map":{…}}` read as key/value pairs). Digits are checked as ASCII `0`–`9` explicitly (never `str.isdigit()`) and at most 16 are accepted **before** `int()` is called. A `Decimal` text is converted with `Decimal(text)` and must then be `is_finite()` (a context with the invalid-operation trap off returns NaN silently); `decimal.InvalidOperation`, `ValueError`, `UnicodeDecodeError` and `IndexError` are all mapped to `PayloadError`. The value is built through `Payload.of` (so every construction rule applies) and the result must satisfy `result.canonical() == data`, otherwise `PayloadError`; strictness comes from that comparison, so the parser must reject, not skip, anything it cannot reject by comparison (whitespace in particular).
- [ ] **Step 4: Remove the `xfail` from `test_copy_and_pickle_round_trip`; run** the payload tests, then `make check`. Expected: PASS and green.
- [ ] **Step 5: Docs.** Extend the revision 9 row (decoder).
- [ ] **Step 6: Commit** `feat(domain): strict decoder for the canonical payload form`.

### Task 3: Cross-process stability

**Files:**
- Create: `tests/support/encode_corpus.py` (child script), `tests/domain/test_payload_stability.py`

**Interfaces:**
- Consumes: Tasks 1 and 2 (`VECTORS`, `CORPUS`, `Payload`).
- Produces: nothing for later tasks.

- [ ] **Step 1: Write `tests/support/encode_corpus.py`.** Run as a script with one argument (`default` or `odd`). It loads `tests/support/vectors.py` by **absolute** file path with `importlib.util.spec_from_file_location`, registering the module in `sys.modules` **before** `exec_module` (otherwise dataclasses with string annotations fail), applies the profile with `decimal.setcontext` (`odd`: `capitals=0`, `prec=3`, `rounding=ROUND_DOWN`, all traps enabled) and prints, per `VECTORS` and `CORPUS` entry, `<id> <hex of canonical bytes>` and a second line `<id>.again <hex of from_canonical(...).canonical()>`. Entry ids contain no whitespace.
- [ ] **Step 2: Write `tests/domain/test_payload_stability.py`:**
  - `test_encoding_is_identical_across_processes` (parametrized over `(hash_seed, profile)` = `("0", "default")`, `("1", "odd")`, `("4242", "odd")`): run `[sys.executable, "-P", str(script), profile]` with `env={"PYTHONHASHSEED": seed}`, `check=True`, `capture_output=True`; compare line by line with the in-process encoding of the same entries; for `VECTORS` also with the expected bytes; each `.again` line equals its first line.
  - `test_child_process_honours_the_hash_seed`: `[sys.executable, "-P", "-c", "print(hash('a'))"]` under two seeds prints different values and under one seed the same value (guards the harness: `-I` would silently ignore the seed).
- [ ] **Step 3: Run** `uv run pytest tests/domain/test_payload_stability.py -v`. Expected: PASS (if a profile produces different bytes the encoder reads the `decimal` context: fix Task 1 code, not the test).
- [ ] **Step 4: `make check`**, extend the revision 9 row only if something changed, **commit** `test(domain): payload encoding is stable across processes`.

### Task 4: Time checks and parameters

**Files:**
- Create: `src/sentaris_engine/domain/timing.py`, `src/sentaris_engine/domain/parameters.py`
- Create: `tests/domain/test_timing.py`, `tests/domain/test_parameters.py`

**Interfaces:**
- Consumes: `Payload`, `PayloadError`, `REJECTED` from Task 1.
- Produces:
  - `timing`: `type EpochMs = int`, `type DurationMs = int` (used in the annotations of Tasks 5 and 6), `require_instant(value: object, name: str) -> int` (exact `int`, not `bool`), `require_duration(value: object, name: str) -> int` (exact `int`, `> 0`); both raise `ValueError` naming the argument. Instants are not required to be non-negative and are not checked for alignment to a timeframe (my call: neither is decided).
  - `parameters.Parameters(Mapping[str, str | int | Decimal | bool])` with `Parameters.of(source: dict[str, object] | Payload | Sequence[tuple[str, object]] = ()) -> Parameters` (same accepted sources and errors as `Payload.of`); equality and hash by the canonical bytes of the equivalent payload; null, sequence or mapping values raise `ValueError`.

- [ ] **Step 1: Write tests** (negative cases through `cast(Any, …)`):
  - `test_instant_accepts_int`; `test_instant_rejects_bool` (`True`, `False`), `float`, `str`, `Decimal`, `None`; `test_duration_rejects_zero_negative_and_bool`.
  - `test_parameters_flat_scalars_are_readable`: `Parameters.of({"n": 3, "p": Decimal("0.50"), "flag": True, "s": "x"})["p"] == Decimal("0.50")`, `len == 4`, iteration in key order.
  - `test_parameters_reject_null_sequence_and_mapping`: values `None`, `(1,)`, `[1]`, `{}`, `{"a": 1}`.
  - `test_parameters_reject_what_payloads_reject`: every `REJECTED` entry used as a parameter **value**, and a duplicate pair key.
  - `test_parameters_equality_is_canonical`: `{"a": Decimal("1.0")}` ≠ `{"a": Decimal("1.00")}`; `{"a": 1}` ≠ `{"a": True}`; insertion order irrelevant.
  - `test_parameters_are_immutable`: item assignment raises `TypeError`; the source dict mutated afterwards does not change them.
- [ ] **Step 2: Run** the two files. Expected: FAIL (modules missing).
- [ ] **Step 3: Implement** `timing.py` and `parameters.py` (`Parameters` wraps a `Payload` built by `Payload.of`, then checks that no value is `None`, `tuple` or `Payload`).
- [ ] **Step 4: Run** the tests, then `make check`. Expected: PASS and green.
- [ ] **Step 5: Docs.** Extend the revision 9 row (time checks, parameters).
- [ ] **Step 6: Commit** `feat(domain): time checks and parameters`.

### Task 5: Candle and snapshot

**Files:**
- Create: `src/sentaris_engine/domain/market.py`, `tests/domain/test_market.py`

**Interfaces:**
- Consumes: `require_instant`, `require_duration`, `EpochMs`, `DurationMs`.
- Produces (`sentaris_engine.domain.market`), all frozen dataclasses with `slots=True`:
  - `Candle(open_time_ms: EpochMs, open: Decimal, high: Decimal, low: Decimal, close: Decimal, volume: Decimal, turnover: Decimal | None, conflicted: bool)`. The five numbers must be exactly `Decimal` and finite; `turnover` is `None` or such a `Decimal` (Quasar sends `null` when the venue gave none, contract section 1; it is never computed or defaulted, DR-15); `conflicted` is carried as Quasar sends it and not interpreted (OD-7 stays open). No relation between the numbers is checked and nothing is corrected.
  - `CandleSeries(timeframe_ms: DurationMs, candles: tuple[Candle, ...])` valid only if `candles` is a `tuple` strictly ascending by `open_time_ms`; `CandleSeries.of(timeframe_ms: int, candles: Iterable[Candle]) -> CandleSeries` sorts ascending and rejects duplicate open times.
  - `Snapshot(series: tuple[CandleSeries, ...])` valid only if strictly ascending by `timeframe_ms`; `Snapshot.of(series: Iterable[CandleSeries]) -> Snapshot` sorts and rejects duplicate timeframes; `Snapshot.series_for(self, timeframe_ms: int) -> CandleSeries | None`.
  - The snapshot holds no `as_of` and no instrument identity: `as_of` lives in the evaluation context (Task 6) and instrument identity is OD-4, left for SE-5 (confirmed by the user, 2026-11-10).

- [ ] **Step 1: Write `tests/domain/test_market.py`:**
  - `test_candle_keeps_decimal_text_exactly`: with `Decimal("64210.123456789012345678")`, `candle.close.as_tuple() == value.as_tuple()` and `candle.close == value`.
  - `test_candle_rejects_non_decimal_and_non_finite_values` (parametrized, through `cast(Any, …)`): `float`, `int`, `str`, `None`, `Decimal("NaN")`, `Decimal("Infinity")` in each of `open`, `high`, `low`, `close`, `volume`; the same except `None` for `turnover`; `conflicted="no"`; `open_time_ms=True`.
  - `test_candle_accepts_null_turnover_only`: `turnover=None` is accepted; `open=None` is not.
  - `test_series_sorts_shuffled_input_to_the_same_series`: `CandleSeries.of(300_000, shuffled)` equals the series from sorted input for several fixed permutations.
  - `test_series_rejects_duplicate_open_time`; `test_direct_construction_rejects_unsorted_candles`.
  - `test_empty_series_and_empty_snapshot_are_valid`: `CandleSeries.of(300_000, [])`, `Snapshot.of([])`; `series_for` returns `None` for a missing timeframe.
  - `test_snapshot_sorts_series_and_rejects_duplicate_timeframes`.
  - `test_snapshot_is_immutable`: attribute assignment raises `FrozenInstanceError`; `candles` and `series` are `tuple`s.
- [ ] **Step 2: Run** `uv run pytest tests/domain/test_market.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `market.py` (validation in `__post_init__`, `of` constructors sort with `sorted(..., key=...)`).
- [ ] **Step 4: Run** the tests, then `make check`. Expected: PASS and green.
- [ ] **Step 5: Docs.** `docs/domain.md` section 2 "Built" gains candle and snapshot types; section 9: DR-11 note gains `tests/domain/test_market.py::test_candle_rejects_non_decimal_and_non_finite_values`; revision 9 row extended.
- [ ] **Step 6: Commit** `feat(domain): candle, series and immutable snapshot`.

### Task 6: Result, signal, context and strategy contract

**Files:**
- Create: `src/sentaris_engine/domain/evaluation.py`, `tests/domain/test_evaluation.py`

**Interfaces:**
- Consumes: `Payload`, `Snapshot`, `Parameters`, `EpochMs`, `require_instant`.
- Produces (`sentaris_engine.domain.evaluation`), frozen `slots=True` dataclasses unless noted:
  - `Signal(kind: str, payload: Payload)`: `kind` an exact non-empty `str`, `payload` exactly a `Payload`.
  - `Signals(signals: tuple[Signal, ...])`: a non-empty `tuple` of `Signal`; order is the strategy's and is never sorted.
  - `NoSignal()`; `EvaluationFailure(code: str)`: exact non-empty `str` (taxonomy is open, OD-3; my call: no further format rule).
  - `type Result = Signals | NoSignal | EvaluationFailure`
  - `EvaluationContext(snapshot: Snapshot, parameters: Parameters, as_of: EpochMs)`.
  - `class StatelessStrategy(Protocol)`: read-only attributes `id: str` and `version: str`; `def evaluate(self, context: EvaluationContext) -> Result`.
  - Nothing in this module names or enumerates a signal kind (DR-23).

- [ ] **Step 1: Write `tests/domain/test_evaluation.py`** (negative cases through `cast(Any, …)`):
  - `test_three_outcomes_are_distinct_types`: `{type(signals), type(NoSignal()), type(EvaluationFailure("x"))}` has three elements and `NoSignal() != EvaluationFailure("x")`.
  - `test_signals_must_be_a_non_empty_tuple_of_signals`: an empty tuple, a `list`, a tuple with a non-`Signal`.
  - `test_signal_requires_kind_and_payload`: empty kind, non-`str` kind, a plain `dict` payload.
  - `test_failure_requires_non_empty_string_code`: `""`, `None`, `1`.
  - `test_signal_equality_uses_the_canonical_payload`: payloads `{"a": Decimal("1.0")}` and `{"a": Decimal("1.00")}` give unequal signals; `Signals` order matters.
  - `test_context_requires_exact_types_and_int_as_of`: `as_of=True`, wrong snapshot or parameters type.
  - `test_result_objects_are_immutable`; `test_results_survive_deepcopy_and_pickle`.
- [ ] **Step 2: Run** `uv run pytest tests/domain/test_evaluation.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `evaluation.py` with validation in `__post_init__`.
- [ ] **Step 4: Run** the tests, then `make check`. Expected: PASS and green.
- [ ] **Step 5: Docs.** `docs/domain.md` section 2 "Built" gains result, signal, context and the stateless contract; revision 9 row extended.
- [ ] **Step 6: Commit** `feat(domain): result, signal, evaluation context and strategy contract`.

### Task 7: Application function, probes and end-to-end

**Files:**
- Create: `src/sentaris_engine/application/evaluation.py`, `tests/support/probes.py`, `tests/application/test_evaluate_strategy.py`
- Modify: `docs/domain.md` (sections 2 and 9, revision 9, status line), `CLAUDE.md` ("Current state" line only)

**Interfaces:**
- Consumes: everything from Tasks 1 to 6.
- Produces:
  - `sentaris_engine.application.evaluation.StrategyContractError(Exception)`.
  - `evaluate_strategy(strategy: StatelessStrategy, context: EvaluationContext) -> Result`: raises `StrategyContractError` unless `strategy.id` and `strategy.version` are exact non-empty `str`; calls `strategy.evaluate(context)`; raises `StrategyContractError` unless `type(outcome) in (Signals, NoSignal, EvaluationFailure)`; otherwise returns it unchanged. It catches nothing: an exception raised by a strategy propagates (how a raise is reported next to other strategies is OD-15, SE-2).
  - `tests/support/probes.py`: `ScriptedProbe(id: str, version: str, outcome: Result)` returns `outcome`; `BrokenProbe(id, version, returns: object)` returns `returns` through `typing.cast`; `RaisingProbe(id, version, error: Exception)`; `MutatingProbe(id, version)` tries to change the snapshot it receives and returns `NoSignal()` if nothing raised; `LastCloseProbe(id, version)` reads `context.snapshot.series_for(300_000)`, returns `EvaluationFailure("series_missing")` if it is absent or empty, `EvaluationFailure("invalid_parameters")` if parameter `"limit"` is present and is not a `int` above zero (a bool is not an int), otherwise `Signals((Signal("probe.last_close", Payload.of({"as_of": context.as_of, "close": last.close, "count": len(series.candles)})),))`. Probes contain no market logic.

- [ ] **Step 1: Write `tests/application/test_evaluate_strategy.py`:**
  - `test_each_outcome_is_returned_unchanged`: `ScriptedProbe` with a `Signals`, `NoSignal()` and `EvaluationFailure("x")` returns exactly those objects, three different types.
  - `test_probe_evaluated_end_to_end_from_fixture_snapshot`: a fixture snapshot of 3 candles (last close `Decimal("64210.123456789012345678")`) through `LastCloseProbe` yields one signal whose `payload.canonical()` is the exact expected bytes with the close text exact.
  - `test_repeated_evaluation_is_deeply_equal`: two evaluations of one context give equal results and identical canonical bytes (DR-13).
  - `test_shuffled_candle_order_gives_the_same_result`: snapshots built from permuted candle lists give equal results.
  - `test_probe_fails_when_series_is_missing`: an empty snapshot and an empty series both give `EvaluationFailure("series_missing")`, not `NoSignal` and not an exception.
  - `test_invalid_parameters_are_a_failure_not_an_exception`: `limit` of `0`, `-1`, `True`, `"3"` gives `EvaluationFailure("invalid_parameters")`.
  - `test_non_result_is_contract_error` (parametrized): `None`, `{}`, `[]`, `"no signal"`, `False`, a bare `Signal` raise `StrategyContractError`.
  - `test_invalid_identity_is_contract_error`: empty `id`, empty `version`, non-`str` id.
  - `test_strategy_exception_is_not_swallowed`: `RaisingProbe` with `RuntimeError("boom")` propagates the same exception.
  - `test_snapshot_cannot_be_mutated_by_a_strategy`: `MutatingProbe` fails (an error from the probe's attempt propagates) and the snapshot is unchanged afterwards.
- [ ] **Step 2: Run** `uv run pytest tests/application -v`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement** `application/evaluation.py` and `tests/support/probes.py`.
- [ ] **Step 4: Run** `uv run pytest -v`, then `make check`. Expected: every test PASS and all four checks green.
- [ ] **Step 5: Docs.** `docs/domain.md`: section 2 "Built" names stateless evaluation of one strategy over a hand-built snapshot (strategies, Quasar snapshot building, scanning and replay stay "Planned"); section 9 removes "No rule has this status yet", sets DR-14 to `ENFORCED` with evidence `tests/application/test_evaluate_strategy.py::test_non_result_is_contract_error`, and leaves every other rule as it is unless it has a named negative test; revision 9 row completed; status line says revision 9. `CLAUDE.md`: replace the "Current state" sentence so it says what exists now (domain types, canonical payload, stateless evaluation of one strategy) and what still does not (no Quasar client, snapshot building, stateful strategies, multi-strategy execution, persistence, replay, scanning, REST).
- [ ] **Step 6: `make check`** and **commit** `feat(application): evaluate a stateless strategy`.

---

## Self-review (done against the spec)

- Spec acceptance for SE-1: three distinct outcomes (Tasks 6, 7); snapshot immutable (Tasks 5, 7); no engine type enumerates a kind (Task 6); canonical form identical in every process and round trips exact (Tasks 1 to 3); strict decoder with each negative test (Task 2). Observable: `uv run pytest -v` lists `test_probe_evaluated_end_to_end_from_fixture_snapshot` (plain `make test` prints only dots).
- Decisions confirmed by the user (2026-11-10): iterative implementation with no depth bound; no instrument in the SE-1 context.
- Calls that are mine, to be checked: `Candle.turnover` nullable and `conflicted` carried uninterpreted; `StrategyContractError` for a non-result and exceptions propagating until SE-2; `StatelessStrategy` lives in `domain`; null, sequence or mapping parameter values are a construction error, strategy-specific invalidity is a failure; DR-11 not marked `ENFORCED` before the Quasar client exists, DR-14 is; instants unconstrained beyond exact `int`, durations `> 0`; failure code has no format rule; hand-written encoder and decoder instead of `json`; branch `se-1-stateless-evaluation`.
- Not in SE-1 by design: stateful contract, several strategies, Quasar client, availability, validation, persistence.
