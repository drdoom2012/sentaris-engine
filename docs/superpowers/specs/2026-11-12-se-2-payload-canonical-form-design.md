# SE-2 — Payload values and canonical form: design

**Slice:** SE-2 (`docs/roadmap.md`, Phase A)  
**Status:** Revision 3. Revision 2 followed one Opus review (`slice-reviewer`: approved with changes, 1 HIGH, 5 MEDIUM, 7 LOW, all addressed). Revision 3 answers the user's focused review (2026-11-12): empty-mapping form, shared references and cycles, decoder exception handling, test budget; it was reviewed by Opus (`slice-reviewer`: approved with changes, 2 MEDIUM, 6 LOW, all addressed; scoped re-review: all addressed, 2 new LOW, addressed). Approved by the user (2026-11-12).  
**Domain references:** section 6.3; Appendix A (A.1, A.2, A.3); DR-10, DR-11, DR-13; OD-25 (not decided here, see section 12)

Decisions marked **[user]** were given by the user in the SE-2 conversation (section 12). Everything marked "my call" is an implementation choice the builder may keep or improve without changing behavior. Names of modules, classes and functions in this document are indicative; the behavior is what is specified.

## 1. Goal

The engine's payload type: the immutable value a signal carries (section 6.3). Construction accepts exactly the values of Appendix A.1 and rejects everything else; it freezes by copy and rejects duplicate keys. Every payload has one canonical byte form (A.2), produced by the engine's own encoder and read back by a strict decoder that accepts only canonical bytes. Payload equality and hashing are by canonical form. All test vectors of A.3 pass. No signal type, no parameters type, no strategy (those are SE-3 and SE-4).

## 2. Why this shape

Appendix A is normative and complete for the accepted values and the encoding; this slice adds no behavior beyond it. The choices below are observable but each follows from the domain document or is a Python API matter; none settles an `OD-xx` (checked in review):

| Choice | Derivation |
|---|---|
| A cyclic container is rejected | Section 6.3: every payload has exactly one canonical form, a byte string, so it is finite; a cyclic container has none. Fail closed. |
| Mappings iterate in canonical key order | DR-10, and equality by canonical form: the mapping kind of A.1 has no order, so construction order must not be observable. |
| The decoder takes exactly `bytes` | API input type; A.2 defines a byte string. |
| Hash derived from the canonical form | Python requires a hash consistent with `__eq__`; equality is by canonical form (6.3). |
| `repr` shows the canonical form | Display only. |
| Rejection message content is free | Section 6.7 never reports a message. |
| Construction from a `list`/`tuple` of 2-tuples | A.3 requires "a mapping built from `[("a", 1), ("a", 2)]`" to be rejected, so such a construction must exist; the exact accepted shapes are an API choice. |
| A scalar predicate exposed for SE-3 | Scope only: section 6.5 says parameter scalars are accepted exactly as payload scalars. |

The one point Appendix A leaves to the implementation that would change behavior, an implicit depth bound, was taken to the user because it touches OD-25 (section 12, U1).

## 3. Scope

1. A module in `sentaris_engine.domain` (my call: `domain/payload.py`) holding: the engine's immutable mapping type, whose constructor is the only entry point that builds a payload (validation and freezing); the canonical encoder; the strict decoder; the rejection error; the scalar predicate.
2. Tests: all A.3 vectors, both directions; every rejection of A.1 and A.3; freezing; duplicate keys; equality; string escaping; key ordering; decoder strictness; context independence; process independence; no implicit depth bound; the scalar predicate.
3. `CLAUDE.md` "Current state": say that SE-2 exists (payload values and canonical form).

## 4. Dependencies

SE-1 (merged on `main` at `d71c170`, `make check` passing). No gate. The module lives in pure code and imports only modules on the pinned pure-stdlib allowlist (expected: `collections.abc`, `decimal`, `typing`, possibly `types`); no architecture list is widened. No new dependency, runtime or dev.

## 5. Interfaces and contracts

### 5.1 Types

- **`FrozenMapping`** (name indicative): the engine's own immutable mapping type of A.1. It is both the type of a payload (a payload is its top-level mapping, A.2) and the type of every nested mapping inside one. It is a real subclass of `collections.abc.Mapping` with `str` keys, so `isinstance(x, Mapping)` holds; the ABC's `__eq__` is overridden (section 5.2) and `__hash__` is defined explicitly.
  - **Construction.** `FrozenMapping(source)` is the only public way to build a payload. `source` is exactly one of:
    - a `dict` (exact type);
    - a `FrozenMapping` (returned as an equal value; my call whether the same object);
    - a `list` or `tuple` (exact types) of pairs, each pair exactly a `tuple` of length 2 whose first element is a key under A.1. An empty `list` or `tuple` gives the empty mapping.
    Anything else is rejected, including a scalar, `None`, a generator or other iterable of pairs, a `list` or `tuple` containing an element that is not a 2-tuple (a `list` pair, a tuple of length 1 or 3, a scalar), and a pair whose key is not exactly a `str`. Pairs with a repeated key are rejected (A.1 "Duplicate keys"); no occurrence wins. My call: no keyword-argument construction, so there is a single path that sees every key.
  - Nested `dict` values become `FrozenMapping` values internally, without going through the public constructor a second time (section 5.3, linear cost). Nested values are always given as `dict` or `FrozenMapping`; a `list` of pairs at a nested position is a sequence, not a mapping.
  - Iteration (`keys`, `values`, `items`, `iter`) is in canonical key order (code-point order, A.2), never in construction order (DR-10).
  - No mutation of any kind: item assignment, deletion and attribute assignment fail, and there is no `__dict__` (my call: `__slots__`, `__setattr__` / `__delattr__` raise; internal initialisation and the bytes cache use `object.__setattr__`).
  - It cannot be subclassed (A.1: a subclass of an accepted type is not that kind). My call: `__init_subclass__` raises.
- **Frozen values.** After construction every reachable value is exactly one of: `None`, `bool`, `int`, `str`, `decimal.Decimal`, `tuple` (of frozen values), `FrozenMapping`. A `list` becomes a `tuple`; a `tuple` is copied into a new `tuple` of frozen values; a `dict` becomes a `FrozenMapping`. A `FrozenMapping` given as a value is reused as is (already frozen and validated). A container that appears at several places without a cycle is accepted. It is frozen once and its frozen copy is shared by every place that refers to it, by memoising on the source object's identity during one construction; this is required by the linear cost of 5.3. Every place is immutable and equal to its source.
- **Shared reference versus cycle.** Construction keeps two distinct records per source container (`list`, `tuple`, `dict`), keyed by object identity and valid for one construction only (the source structure keeps every keyed object alive for its duration):
  - **in progress**: the container has been entered and not all of its contents are frozen yet, so it is an ancestor of the position being visited. Reaching an in-progress container again is a cycle and is rejected.
  - **finished**: the container is completely frozen; its frozen result is memoised. Reaching a finished container again is a shared reference: the memoised frozen value is reused and the container is not visited again.
  The traversal is depth-first: a container is marked in progress when the traversal **enters** it (not when it is pushed onto the work stack as a pending child), and marked finished when its last child has been frozen. Only then is "in progress" the same as "ancestor of the current position"; marking on push would reject siblings. A container moves from in progress to finished exactly once. A container reached a second time is therefore classified by its state at that moment, never by "seen before", so a sibling or a diamond (two paths to one node) is accepted and only a path back to an ancestor is rejected. Detection is part of the explicit work stack (section 5.3), so it works at any depth.
- **Rejection error** (my call: one exception class, a subclass of `ValueError`, raised by construction and by decoding). Its message names the reason; its content is otherwise free (it may name the position, for example a path or a byte offset). Tests assert the exception class only, never the message. Section 6.7 never reports a message.

### 5.2 Operations

| Operation | Contract |
|---|---|
| Construct `FrozenMapping(source)` | Accepts exactly the values of A.1 under the rules of A.1 (exact type match, integer range, no surrogate code point in any `str`, keys included, finite `Decimal`, keys exactly `str`, duplicate keys rejected) and the source shapes of 5.1. Freezes by copy. Rejects a cyclic container (a `list`, `tuple` or `dict` that contains itself, directly or indirectly). |
| Canonical form `canonical_bytes()` (method or function) | Returns the bytes of A.2 for the payload's top-level mapping. Exactly A.2: no `json` module, no `str(Decimal)` or `format()` of a `Decimal`, no `repr`. Never reads or depends on the `decimal` context. My call: the result is cached on the mapping it was requested for. |
| Decode `decode(data)` | Accepts exactly `bytes` (`bytearray`, `memoryview`, `str` and everything else are rejected). Returns the `FrozenMapping` whose canonical form is `data`. Rejects every input that is not the canonical form of some payload (A.2 "Required properties") with the rejection error; for malformed or non-canonical data no other exception type escapes. Process-level failures such as `MemoryError` are not data and propagate unchanged (section 5.6). |
| Equality `==` | Two `FrozenMapping` values are equal exactly when their canonical forms are equal (section 6.3, A.1 "Equality"). Comparison with any other type returns `NotImplemented` (so `FrozenMapping({}) == {}` is `False`). |
| Hash | Consistent with equality: derived from the canonical form. A hash value is never part of any output (it varies by process). |
| `repr` | Shows the canonical form as text. Safe at any depth (section 5.3). |
| Scalar predicate | `is_payload_scalar(value) -> bool` (name indicative), used by construction and exposed for SE-3. Returns `True` exactly for the four scalar kinds of A.1 (exact `bool`; exact `int` in range; exact `str` without a surrogate code point; exact finite `Decimal`) and `False` for everything else, `None` and every container included. It never raises. |

### 5.3 No implicit bound, linear cost **[user U1]**

No depth or size bound on a payload is decided (section 6.3, OD-25), and the implementation must not introduce one implicitly. Construction (validation, cycle detection, freezing), encoding, decoding, equality, hashing and `repr` are implemented **without recursion over the payload structure**, with an explicit work stack. Equality and hashing go through the canonical bytes, never through Python equality or hashing of nested tuples (which recurse in C and fail with `RecursionError` at depth). The only limit is memory. Tests never raise `sys.setrecursionlimit`.

**Linear cost (my call, needed for U1 to be usable).** Construction takes time linear in the number of distinct source containers plus the total number of their entries (plus the cost of sorting each mapping's keys): because of the memo of 5.1, a shared container is frozen once however often it is referenced. Encoding takes time linear in the length of its output, and decoding (parse plus re-encoding) linear in the length of its input. A structure that shares containers heavily (a directed acyclic graph) is cheap to construct, but its canonical form expands every reference, so its encoding may be much larger than its construction; that is a property of A.2, not a bound, and no limit is introduced for it (U1). In particular: nested mappings are not re-validated, and encoding a mapping does one pass over its structure; it does not compute or cache the canonical bytes of each nested mapping separately, because caching every level would cost quadratic memory for a deep chain. A nested mapping computes its own bytes only when asked (for its own `==`, `hash` or `repr`). `make check` stays within the 60 s of SE-1 AC-9.

### 5.4 Decimal text

The `$decimal` text is the *to-scientific-string* conversion of the General Decimal Arithmetic Specification, computed from `Decimal.as_tuple()` (sign, coefficient digits, exponent) with an uppercase `E`. Python's `str(Decimal)` reads `capitals` from the current context, which is why it is not used (A.2, A.3 "`capitals = 0` included"). For a finite value with coefficient digits `c` (length `n`, no leading zeros except the single digit of a zero coefficient) and exponent `e`, adjusted exponent `a = e + n − 1`:

- if `e = 0`: the digits `c` alone (`Decimal("100")` and `Decimal("1.00E+2")` both give `100`);
- if `e < 0` and `a ≥ −6`: plain notation with a decimal point before the last `−e` digits; if `−e ≥ n`, the text is `0.`, then `−e − n` zeros, then `c` (`Decimal("0.0005")` gives `0.0005`, `Decimal("0E-3")` gives `0.000`);
- otherwise (`e > 0`, or `a < −6`): scientific notation: `c[0]`, then `.` and the remaining digits if `n > 1`, then `E`, then the sign of `a` (always present: `+` for `a ≥ 0`, `-` for `a < 0`), then the digits of `|a|` (`Decimal("1E+2")` gives `1E+2`, `Decimal("0E+3")` gives `0E+3`, `Decimal("0.0000001")` gives `1E-7`).

A leading `-` for a negative sign, `-0` included. This must equal `str(d)` under the default context for every finite `d`; a test compares the two over the A.3 values and a generated set (section 8, N7).

### 5.5 Decoder strictness

My call on the method: a parser of its own (no `json` module, which is not on the pure-stdlib allowlist) builds the candidate payload with an explicit stack, then the decoder re-encodes the candidate and requires the result to be byte-identical to the input. The re-encoding check is what guarantees "accepts only canonical bytes"; the parser may be lenient in ways the re-encoding catches, but it must never produce a value outside A.1, and every malformed or non-canonical input must end in the rejection error. Numbers are never parsed through `float` (DR-11). A `Decimal` is built from its text, which is exact and context-independent for construction from a string; with traps disabled malformed text yields NaN, which the finiteness check and the re-encoding reject.

The decoder builds every `Decimal` through **one module-level name** used for nothing else (for example `_decimal_from_text = Decimal`, or a small function), so that N16 can replace it in a test. No `except` clause looks a class up through that name. My call: the conversion runs inside `decimal.localcontext()`, so that decoding malformed text does not set the `InvalidOperation` flag on the caller's context; the outcome, a rejection, is the same either way.

### 5.6 Exception handling

The rejection error is for **data**: malformed or non-canonical bytes in the decoder, and values outside A.1 or bad source shapes in construction. Failures of the process are not data and are never turned into it.

- **Detected, not caught, where possible.** The parser checks bounds and structure explicitly (end of input, expected byte, token shape) and raises the rejection error itself; it does not rely on catching `IndexError` or `KeyError` from its own indexing. An integer token is checked in two steps: before `int()`, its shape (optional `-`, no leading zero, ASCII digits only) and its length (at most 16 digits; 2^53 − 1 has 16), so neither Python's integer string-length limit nor a large conversion is reached; after `int()`, the exact range ±(2^53 − 1), which the 16-digit values above it fail.
- **Translated, narrowly.** Only the specific exceptions that a library call raises for invalid data are translated into the rejection error, each at the one call that raises it: `UnicodeDecodeError` from strict UTF-8 decoding of the input, `UnicodeEncodeError` from the surrogate check if it is done by encoding, `decimal.InvalidOperation` from `Decimal(text)`. The translation chains the original (`raise … from`).
- **Never caught.** No `except:` without a class, and no handler for `Exception`, `BaseException`, `ArithmeticError`, `LookupError`, `MemoryError`, `RecursionError`, `SystemError`, `KeyboardInterrupt`, `SystemExit` or `GeneratorExit`, anywhere in the module. `MemoryError` and every other process-level failure propagate unchanged from construction, encoding and decoding. (A `RecursionError` cannot arise from the payload structure under 5.3; if one arises anyway, it propagates and fails N11 visibly.)
- **Construction** follows the same rules: it raises the rejection error for values and shapes, and catches nothing else.

The set of exception classes a handler may name is fixed in the plan from the list above and checked by N16. Handlers name their classes by literal spelling only (no alias variable, call or subscript), so the static check cannot be bypassed by aliasing.

## 6. Expected behavior

- Every A.3 vector: constructing the Python payload gives exactly the listed bytes, and decoding the listed bytes gives a payload equal to it whose canonical form is those bytes.
- The `Decimal` vectors give identical bytes under the default context and under altered contexts (`capitals = 0`, low `prec`, other `rounding`, `Emax`/`Emin` narrowed, traps changed), set with `decimal.localcontext()`.
- Every value on A.3's "Rejected at construction" line and every rejected kind of A.1 is rejected with the rejection error, at the top level and nested.
- `{"a": True}` and `{"a": 1}` differ; `Decimal("1.0")`, `Decimal("1.00")` and `Decimal("1E+1")` differ; `Decimal("0")` and `Decimal("-0")` differ; `"1"`, `1`, `True`, `Decimal("1")` and `None` give five different payloads. A `list` and a `tuple` with the same elements give equal payloads. Two `dict` sources with the same entries in different insertion order give equal payloads with the same bytes and the same iteration order.
- Changing a source `list` or `dict` after construction changes nothing in the payload.
- A container referenced from several places without a cycle (siblings, a diamond, a reference at a different depth) is accepted and gives the same payload as separate equal copies; a container that contains itself, directly or through any chain, is rejected.
- The empty mapping's canonical form is `{"$map":{}}` (A.2 mapping row, first A.3 vector); `{"$map":[]}` is the canonical form of no payload and is rejected by the decoder.
- A payload nested well beyond Python's recursion limit can be constructed, encoded, decoded, compared, hashed and `repr`-ed, and round-trips.

## 7. Acceptance criteria

| AC | Criterion |
|---|---|
| AC-1 | All eight A.3 vectors pass in both directions (construct → bytes; bytes → decode → equal payload, re-encodes identically). |
| AC-2 | Every A.3 rejected value and every A.1 rejected kind is rejected at construction with the rejection error (N1, N2). |
| AC-3 | The `Decimal` vectors and a generated set of `Decimal` values give identical bytes under every altered context of section 6; the text equals `str(d)` under the default context (N7). |
| AC-4 | Freezing by copy: no mutable object reachable through the public interface; mutation of the source has no effect; the mapping type cannot be mutated or subclassed (N4). |
| AC-5 | Duplicate keys from pairs are rejected; bad source shapes are rejected (N2, N3). |
| AC-6 | Equality and hash by canonical form, including the pairs of section 6 that Python equality would confuse (N5). |
| AC-7 | The decoder rejects every non-canonical input of N6, raising only the rejection error. |
| AC-8 | Round trip: for a seeded generated set of payloads (my call: a deterministic generator in the tests using `random.Random(seed)`, no new dependency), `decode(canonical_bytes(p)) == p` and its bytes are identical. |
| AC-9 | No implicit depth bound (N11). |
| AC-10 | Process independence: the canonical bytes of a fixed set of payloads are identical in two subprocesses run with different `PYTHONHASHSEED` values (N10). |
| AC-11 | String escaping and key ordering exactly as A.2 (N13, N14). |
| AC-12 | The scalar predicate returns `True` exactly for the four scalar kinds and never raises (N15). |
| AC-13 | `make check` passes within the SE-1 time budget, and the SE-2 tests stay within the budget of section 8.1; the payload module is under the SE-1 purity checks (it is found by the real-tree check of `tests/architecture/test_purity.py`) without widening any list. |
| AC-14 | Shared references without a cycle are accepted and a shared container is frozen once; true cycles are rejected at any depth (N12, N17). |
| AC-15 | Exception handling as section 5.6: data errors raise the rejection error; no broad or process-level handler exists in the module; `MemoryError` propagates (N16). |

## 8. Negative tests

One named test (or parametrised test) per rule this slice claims to enforce. Names are indicative; the plan fixes them. Rejection tests assert the exception class only.

| # | Rule | Test | Fails when |
|---|---|---|---|
| N1 | A.1 accepted values; section 6.3 | `test_rejected_value_is_refused`, parametrised over: `float`; `Decimal` NaN, sNaN, Infinity, −Infinity; `int` 2^53 and −2^53; `bytes`; `bytearray`; an `IntEnum` member, a `(str, Enum)` member, a plain `Enum` member; instances of subclasses of `str`, `int`, `Decimal`, `dict`, `list`, `tuple`; `set`; `frozenset`; a generator; an iterator; `range`; `object()`; `MappingProxyType`; `OrderedDict`; a non-`str` key (`1`, `True`, `None`, a `str` subclass instance); a `str` value and a key containing a surrogate code point. Each at the top level (as a value), inside a `list`, inside a `tuple`, as a value of a nested `dict` and as a value of a nested `FrozenMapping`. The list is representative of "no other type is a payload value", not exhaustive. | any is accepted |
| N2 | A.1 top level; source shapes of 5.1 | `test_bad_source_is_refused`: a scalar, `None`, a `set`, a generator of pairs, a `list` containing a scalar, a `list` pair (`[["a", 1]]`), pairs of length 1 and 3, a pair with a non-`str` key, `OrderedDict`, `MappingProxyType`; positive companion `test_empty_pairs_give_empty_mapping` (`[]`, `()`) | a bad source is accepted |
| N3 | A.1 duplicate keys | `test_duplicate_key_from_pairs_is_refused` (also with a duplicate inside a nested pair-built `FrozenMapping` given as a value) | accepted, or one occurrence wins |
| N4 | A.1 freezing by copy | `test_source_mutation_does_not_change_payload`, `test_no_mutable_value_is_reachable` (walks every reachable value through the public interface), `test_mapping_cannot_be_mutated`, `test_mapping_cannot_be_subclassed` | a change of the source shows, a `list`/`dict` is reachable, assignment succeeds, a subclass can be defined |
| N5 | A.1 equality; section 6.3 | `test_equality_is_by_canonical_form` (`True`/`1`, `1.0`/`1.00`, `0`/`-0`, the five values of A.2; `FrozenMapping({}) != {}`); `test_hash_follows_equality` | Python equality decides, or equal values hash differently |
| N6 | A.2 strict decoder | `test_non_canonical_bytes_are_refused`, parametrised over at least: empty input; truncated input; trailing byte; trailing newline; BOM; whitespace between tokens; unsorted keys; duplicate keys; an untagged object; an unknown tag; `$map` with a second key; `{"$map":[]}` (an array where A.2 requires the entries object; the empty mapping is `{"$map":{}}`, accepted by `test_vectors`); `$decimal` with a second key; `{"$decimal":1}`; a top-level non-mapping (`[]`, `null`, `"x"`, `1`, `{"$decimal":"1"}`); `\/`; `\u0041`; `\u0008` where `\b` is canonical (and likewise for `\t`, `\n`, `\f`, `\r`); uppercase hex in `\u001F`; escaped DEL `\u007f`; `\u0022` and `\u005c` for `"` and `\`; `\u00e9` for `é`; a raw control byte; a lone `\ud800`; the surrogate pair `\ud83d\ude00` for U+1F600; invalid UTF-8; overlong UTF-8 (`C0 80`); UTF-8-encoded surrogate (`ED A0 80`); integer with a leading zero, `-0`, `+1`, `1.5`, `1e2`, 2^53, a 5000-digit integer; `$decimal` text `1e2`, `1E2`, `+1`, `01`, `.5`, `1.`, `NaN`, `Infinity`, `1_0`, a non-ASCII digit, `1.00E+2` (a value whose canonical text is `100`); `True` and `NULL`; a non-`bytes` argument (`str`, `bytearray`, `memoryview`). | any is accepted, or an exception other than the rejection error escapes |
| N7 | A.2 `Decimal` text; context independence; DR-13 | `test_decimal_text_ignores_context` (altered contexts of section 6, `capitals = 0` first); `test_decimal_text_matches_default_str` (A.3 values and a generated set, covering `e = 0`, `e < 0`, `−e ≥ n`, `a < −6`, `e > 0`, zero coefficients with positive and negative exponents, negative zero) | bytes differ under a context, or the text differs from `str(d)` under the default context |
| N8 | DR-10 | `test_construction_order_does_not_change_form_or_iteration` (permuted `dict` sources and pair lists) | bytes or iteration order differ |
| N9 | DR-11 | covered by N1 (`float` refused at every position) and N6 (`1.5`, `1e2` refused); plus `test_decoder_never_yields_float` over the generated round-trip set | a `float` is accepted or produced |
| N10 | DR-13 (process part) | `test_canonical_form_is_identical_across_processes` | the subprocess outputs differ |
| N11 | Section 5.3 **[user U1]** | `test_no_implicit_depth_bound`, parametrised over three shapes (sequence-only, mapping-only, alternating), depth `max(10 × sys.getrecursionlimit(), 10 000)` read at test time: construct, encode, decode, `==`, `hash`, `repr`, round trip | `RecursionError` or any other failure |
| N12 | A.1 cycles | `test_cyclic_container_is_refused`. Cases: a `list` containing itself; a `dict` containing itself as a value; a cycle through a `tuple` holding a `list` (`l = []; l.append((l,))`); an indirect cycle of length 3 (`dict` → `list` → `dict` → first `dict`); a cycle whose back edge leaves a shared node (a diamond whose bottom node refers back to the top); a cycle closed at depth `max(10 × sys.getrecursionlimit(), 10 000)`; and the linear-cost case of N17 (b). All cases run in **one** subprocess with a timeout (my call: 20 s), so that a hang fails the test instead of blocking the run. The subprocess runs every cycle case first, printing and flushing each case's result as soon as it is known, and runs N17 (b) last, so that a hang or memory growth in (b) cannot lose the cycle results; N17 (a) already catches a missing memo in process, so (b) is there for superlinear cost of any other cause. The subprocess reports, per case, the name of the exception class raised (or that none was raised); the test asserts that each cycle case raised exactly the rejection error and that the N17 (b) case finished without an exception | any cycle case is accepted or ends in an exception other than the rejection error (a missed cycle that grows the work stack until `MemoryError` included), the N17 (b) case raises, or the subprocess does not finish within the timeout |
| N13 | A.2 string row | `test_string_escaping` (encoder direction): each of the 32 code points U+0000 to U+001F (the five short escapes `\b`, `\t`, `\n`, `\f`, `\r`, the rest as `\u00xx` lowercase), `"`, `\`, U+007F, a BMP non-ASCII character and an astral character, each in a value and in a key, against its exact expected bytes | any byte differs |
| N14 | A.2 mapping row | `test_key_order_is_by_code_point` (keys `"a"`, `"ab"`, `"b"`, `"Z"`, U+FFFF and U+1F600, which UTF-16 order would sort differently, and a proper prefix) | order differs |
| N15 | Section 5.2 scalar predicate (for section 6.5) | `test_scalar_predicate`: `True` for each scalar kind and the integer bounds ±(2^53 − 1); `False` for `None`, `tuple`, `list`, `dict`, `FrozenMapping` and every scalar-like rejected value of N1; never raises | a wrong answer or an exception |
| N16 | Section 5.6 | `test_module_catches_no_process_failure` parses the payload module's AST: every `except` and `except*` handler names its classes by literal spelling only (a `Name` or a dotted `Attribute`, alone or in a literal tuple), each from the plan's fixed set; any other handler expression (an alias variable, a call, a subscript) is a violation, as are a bare `except` and every class listed as never caught in 5.6. The same test rejects any binding in the module (assignment, augmented or annotated assignment, `import … as`, `from … import`, function or class definition, `global`) of a name that is in the fixed set or in the never-caught list, so an allowed name cannot be rebound to a broad class. `test_memory_error_propagates` monkeypatches the module-level name through which the decoder constructs a `Decimal` (5.5) so that it raises `MemoryError`, then decodes a valid payload holding a `Decimal`; the caller receives `MemoryError`, not the rejection error | a non-literal, broad or process-level handler exists, or `MemoryError` arrives as the rejection error |
| N17 | Section 5.1 shared reference | `test_shared_container_is_accepted`, parametrised over: one `list` as two sibling values of a `dict`; one `dict` as two elements of a `list`; a diamond (two nested containers referring to one third); one container referenced at two different depths; a shared container inside a shared container. Each gives a payload equal to (same canonical bytes as) the same structure built from separate copies, and is immutable (N4's walk). `test_shared_container_is_frozen_once` has two parts: **(a)** in process, a 4-level chain in which each level holds the next level twice; at every level the two frozen children are the same object (`is`); without the memo this finishes at once and fails on `is`; **(b)** the linear-cost case, a 30-level chain of the same form (2^30 paths, 30 distinct containers), constructed inside N12's subprocess under its timeout and counted as failed if it does not finish. Neither part encodes, compares, hashes or `repr`s the chain payload: each of those goes through the canonical form, which expands every path (section 5.3) | a shared reference is rejected or gives a different payload, (a) finds two distinct frozen children, or (b) does not finish within N12's timeout |

The A.3 vectors themselves are a positive test (`test_vectors`, parametrised over the eight lines, both directions).

### 8.1 Test budget

U1 stays: no implicit depth limit, and the deep tests run in the standard suite on every `make check`. Their size is fixed so that the suite stays cheap:

- N11 and the deep case of N12 use depth `max(10 × sys.getrecursionlimit(), 10 000)` (10 000 under the default limit), not more. That is far enough beyond the recursion limit to show there is no implicit bound; a larger depth would show nothing more, because the implementation is iterative and linear (5.3).
- The generated sets (AC-8, N7, N9) use a fixed seed and a fixed size (my call: 500 payloads, 1 000 `Decimal` values).
- Subprocesses: N10 starts two; N12 starts one, which runs all of its cases and N17 (b); no other test starts one.
- Budget: all SE-2 tests together add at most 5 s to `make check` on the development machine, measured by the orchestrator at slice completion and recorded in the slice report. If the budget is exceeded, the slice is not accepted until the cost is reduced (for example by sharing constructed deep payloads between the assertions of N11), and never by reducing coverage: the three shapes, the depth formula, the operations checked and the listed cases stay.
- No stress tier (`slow` marker) is added in SE-2.

## 9. Enforced guarantees and known limitations

Enforced after this slice, each by the negative tests above: the accepted and rejected values of A.1 (N1, N2, N12, N17); exception handling of 5.6 (N16); duplicate keys (N3); freezing by copy through the public interface (N4); equality by canonical form (N5); the canonical form of A.2 (A.3 vectors, N7, N8, N13, N14); the strict decoder (N6); the parts of DR-10, DR-11 and DR-13 named in section 8 (N8, N9, N10, N7); no implicit depth bound (N11).

Convention or review only:

- **Reachability through private attributes.** "Nothing mutable is reachable" holds through the public interface. Python cannot stop code from reaching a private attribute or using `gc.get_referents`; the internal storage is a private attribute, never handed out. Strategies are pure code under the SE-1 checks, which do not detect this.
- **Python operations on values taken from a payload.** Only `FrozenMapping` equality is canonical. A `tuple` taken from a payload compares with Python semantics (`(True,) == (1,)` holds), and comparing or hashing a deeply nested `tuple` with Python's own operators may hit the recursion limit. Both are outside the engine's operations of sections 5.2 and 5.3.
- **Memory.** No bound means a payload is limited only by memory (OD-25 stays open). A payload that shares containers heavily is cheap to construct but its canonical form, and therefore its equality, hash and `repr`, may be exponentially larger (5.3); no limit is introduced for it.
- **Process-level failures.** N16 checks the handlers statically and `MemoryError` at one call site; that no other call site masks a process-level failure rests on the static check.
- **Platform independence** (A.2 "on which platform") cannot be tested in one environment; it rests on the encoder using no platform- or context-dependent operation (5.2, 5.4) and is checked by review.
- DR-10, DR-11 and DR-13 are enforced here only for payloads; later slices enforce them for their own types.

## 10. Exclusions

- The signal type (`kind` plus payload) and signal equality: SE-3.
- Parameters (section 6.5): SE-3; SE-2 only provides the scalar predicate.
- Any depth or size bound (OD-25), and any persistence or transport of canonical bytes (OD-11, OD-20).
- Strategy state encoding (OD-20): the canonical form applies to payloads only.
- No `json` module, no third-party serialization or property-testing library.
- No change to `docs/domain.md` or `docs/roadmap.md`.

## 11. Open questions

None for the user. The review found no point touching an `OD-xx`, a `DR-xx` or section 6 beyond U1.

## 12. Decisions by the user (2026-11-12)

- **U1.** No implicit bound: every payload operation of the engine works without recursion over the payload structure, so any depth that fits in memory is accepted; a negative test with nesting beyond the recursion limit (N11). This does not decide OD-25: whether a bound is needed stays open, and a bound, if one is decided, will be explicit.
