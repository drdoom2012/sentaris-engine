# ADR-0001: Evaluation types and strategy contract

- **Status:** Accepted (approved by the user on 2026-11-10: Gate 1 of the roadmap, each item as proposed). **Amended** 2026-11-10 at the user's request: `docs/domain.md` revision 5 (OD-14 payloads may nest; OD-21 names a primary instrument; OD-22 opened) and revision 6 (OD-14 adds null and fixes the canonical byte format), and revision 8 (OD-14 clarified: which Python values are each kind, freezing by copy, duplicate keys, integer range ±(2^53 − 1), `Decimal` text independent of the `decimal` context; approved by the user on 2026-11-10 after the review recorded in the roadmap, Gate 1).
- **Date:** 2026-11-10
- **Scope:** time representation, result shape, signal representation and its canonical form, strategy identity and contract, parameters, and what one evaluation context covers.
- **Spec:** `docs/superpowers/specs/2026-11-09-engine-roadmap-design.md` (section 5, Gate 1)
- **Decides:** OD-10, OD-14, OD-21; **partly** OD-3 and OD-13; **opens** OD-22 (`docs/domain.md`, section 10)

## Context

Slice SE-1 (stateless evaluation from a hand-built snapshot) needs domain types for time, signal, result, parameters and the strategy contract. `docs/domain.md` left each open, and section 10 forbids deciding them by implementation. The roadmap also found a gap the document did not name: whether one snapshot covers one instrument or several (G-1, recorded here as OD-21).

## Decisions

| ID | Decision | Reason |
|---|---|---|
| OD-10 | Every instant, `as_of` included, is an integer count of UTC milliseconds since the Unix epoch; every duration, such as a timeframe, is integer milliseconds. No timezone-bearing or floating-point time type. | Matches the Quasar contract exactly: no conversion, no time zones, no sub-millisecond values Quasar cannot express. |
| OD-3 (part) | A result is exactly one of: **signals** (a non-empty, ordered tuple of signals), **no signal**, or **evaluation failure** carrying a machine-readable string code. One evaluation may carry several signals. | A closed union keeps DR-14's three outcomes distinct as types. Several signals avoids packing many outputs into one payload. |
| OD-14 | A signal is a strategy-owned string `kind` plus an immutable payload. The payload is a **mapping**. A payload value is recursively one of: **null**; a **scalar** (string, integer, finite `Decimal`, boolean); a **sequence** (immutable, ordered, of payload values); a **mapping** (immutable, unique string keys, of payload values). No other type is a payload value. Every payload has exactly one **canonical form**, the byte string defined below; two payloads are equal exactly when their canonical forms are equal. The engine neither enumerates kinds nor reads payloads. | Strategies need structured outputs, including an explicitly empty slot, without the engine knowing their shape (DR-23). Defining equality by one fully specified byte form makes determinism checks exact (DR-13), keeps `Decimal` exact (DR-11) and leaves nothing for the implementation to decide. |
| OD-13 (part) | A strategy is identified by `id` and `version`, both non-empty strings with no imposed format; a change in behavior is a new version. There are two contracts, one per form in DR-26: stateless (`context → result`) and stateful (`context, previous_state → result, next_state`). Strategies are passed to execution as an explicit list from the composition root; there is no discovery. Parameters are a **flat** immutable mapping from string keys to the scalar values of OD-14 (no null, no nested sequences or mappings); each strategy validates its own, and invalid parameters are an evaluation failure, not an exception. The engine never interprets parameters. | Two contracts mirror DR-25 (a stateless strategy receives no `previous_state`). One flat parameter form lets later slices digest parameters for the state scope (OD-17) without knowing the strategy. Nesting and null stay limited to signal payloads, where they were asked for. |
| OD-21 | One evaluation context has exactly one **primary instrument**: the instrument it is evaluated for and the instrument of its state scope (DR-27). Its snapshot may hold several inputs and timeframes of that instrument, and, until OD-22 is decided, data of no other instrument. | Simplest form, consistent with DR-27, and sufficient for SE-1. Naming the instrument "primary" leaves room for OD-22 without changing what an evaluation is for. |

### Null in a payload (OD-14)

Null is a value a strategy chooses to emit; its meaning belongs to the strategy (DR-23). It is distinct from every other value and from an absent key: `{"a": null}` and `{}` are different payloads. It is a payload value only: it is not a scalar, so it is not a parameter value (OD-13) and not a signal `kind`. Null never stands in for market data that is missing, stale or unavailable; that remains an evaluation failure (DR-14, DR-15).

### Which Python values are payload values (OD-14) — normative

The kinds are matched by exact type; a subclass of an accepted type is not that kind and is rejected.

| Kind | Accepted at construction | Notes |
|---|---|---|
| null | `None` | |
| boolean | exactly `bool` | A boolean is never an integer. |
| integer | exactly `int`, in the range −(2^53 − 1) to 2^53 − 1 inclusive | Outside the range it is rejected. Every consumer, a JavaScript frontend included, then reads it exactly. A larger or exact quantity is a `Decimal`. |
| string | exactly `str`, without a surrogate code point | |
| `Decimal` | exactly `decimal.Decimal`, finite | |
| sequence | exactly `tuple` or `list` | |
| mapping | exactly `dict`, or the engine's own immutable mapping type | Keys are exactly `str`. |

Rejected, among others: `IntEnum`, `(str, Enum)` mixins and every other `Enum`; subclasses of `str`, `int` or `Decimal`; `set`, `frozenset`, generators, iterators and every other collection; `float`; `bytes`; strategy-defined classes. A strategy that holds an enum passes its `.value`.

**Freezing by copy.** Construction copies every accepted container, recursively, into an immutable form owned by the payload. A `list` or `dict` given to construction is therefore accepted, and changing it afterwards does not change the payload. Nothing mutable is reachable from a constructed payload.

**Duplicate keys.** Any construction that is given the same key twice, for example a mapping built from key-value pairs, is rejected; no occurrence wins.

The same rules apply to the scalars of a parameter mapping (OD-13).

### Canonical form of a payload (OD-14) — normative

The canonical form is a UTF-8 byte string, without byte-order mark, without any whitespace outside strings and without a trailing newline. It is valid JSON (RFC 8259) under this profile, so it stays readable, but it is defined here, not by any JSON library. Each value is encoded by its kind:

| Kind | Encoding |
|---|---|
| null | `null` |
| boolean | `true` or `false` |
| integer | Decimal digits with no leading zero and no `+`; `-` before a negative value; zero is `0`. The value lies in −(2^53 − 1) to 2^53 − 1; at most 16 digits. |
| string | `"`, the characters, `"`. Exactly these are escaped: `"` as `\"`, `\` as `\\`, U+0008 `\b`, U+0009 `\t`, U+000A `\n`, U+000C `\f`, U+000D `\r`, and every other code point U+0000 to U+001F as `\u` plus four **lowercase** hex digits. Every other code point, U+007F and non-ASCII included, appears literally as UTF-8. No Unicode normalization is applied. |
| `Decimal` | `{"$decimal":"` + text + `"}`, where text is the *to-scientific-string* conversion of the General Decimal Arithmetic Specification of a finite value, with an uppercase `E`. The text is a function of the value's sign, coefficient digits and exponent alone and never depends on the `decimal` context (`capitals`, precision, rounding, traps); under the default context it equals Python's `str(Decimal)`. It keeps sign, coefficient and exponent exactly, so `1.0`, `1.00` and `1E+1` differ, and so do `0` and `-0`. |
| sequence | `[`, the encoded elements in their given order separated by `,`, `]`. Empty: `[]`. |
| mapping | `{"$map":{` + entries + `}}`. Each entry is the key encoded as a string, `:`, the encoded value; entries are separated by `,` and ordered by the keys' Unicode code points, compared element by element, a proper prefix first (which equals the order of their UTF-8 bytes). Empty: `{"$map":{}}`. |

A payload's canonical form is the encoding of its top-level mapping, so it always starts with `{"$map":{`.

Why the tags: every JSON object in the canonical form is either a one-key tag, `$decimal` or `$map`, or the entries object directly inside a `$map` tag, so a `Decimal`, a string and a mapping can never encode alike, whatever keys a strategy uses; no key is reserved. A `Decimal` is text, never a JSON number, so no consumer can read it as a binary float (DR-11). Integers and booleans use JSON literals, which no other kind produces.

Properties that follow, and that tests must show: the encoding is injective and type-preserving (`"1"`, `1`, `true`, `{"$decimal":"1"}` and `null` are five values); a payload can be reconstructed exactly from its form; the same payload gives the same bytes regardless of how it was built, in which process, under which `decimal` context or on which platform (DR-10, DR-13). A decoder, when one is needed, accepts only bytes that are the canonical form of some payload and rejects anything else, an integer outside the range included.

**Test vectors.** Each line is a payload in Python notation and its exact canonical form.

| Payload | Canonical form |
|---|---|
| `{}` | `{"$map":{}}` |
| `{"b": 1, "a": True}` | `{"$map":{"a":true,"b":1}}` |
| `{"p": Decimal("64210.50"), "q": Decimal("-0"), "r": Decimal("1E+2"), "s": Decimal("0.0000001")}` | `{"$map":{"p":{"$decimal":"64210.50"},"q":{"$decimal":"-0"},"r":{"$decimal":"1E+2"},"s":{"$decimal":"1E-7"}}}` |
| `{"x": None, "y": [], "z": ["1", 1, None, {}]}` | `{"$map":{"x":null,"y":[],"z":["1",1,null,{"$map":{}}]}}` |
| `{"$map": "k", "é": "a\"b\\c\n\x01"}` | `{"$map":{"$map":"k","é":"a\"b\\c\n\u0001"}}` |
| `{"Z": 0, "a": -5, "ab": 2, "aa": 3}` | `{"$map":{"Z":0,"a":-5,"aa":3,"ab":2}}` |
| `{"max": 9007199254740991, "min": -9007199254740991}` | `{"$map":{"max":9007199254740991,"min":-9007199254740991}}` |
| `{"d": Decimal("-1.50E-12"), "t": (True, False)}` | `{"$map":{"d":{"$decimal":"-1.50E-12"},"t":[true,false]}}` |

The `Decimal` vectors give the same bytes under any `decimal` context, `capitals = 0` included.

**Rejected at construction:** `{"n": 9007199254740992}`, `{"n": -9007199254740992}`, `{"n": 1.5}`, `{"n": Decimal("NaN")}`, `{"s": {1, 2}}`, `{"e": IntEnum member}`, `{"e": (str, Enum) member}`, `{1: "a"}`, a mapping built from `[("a", 1), ("a", 2)]`.

### What is not a payload value

Construction rejects, and nothing in the engine produces: every value outside the table "Which Python values are payload values"; in particular `float`; non-finite `Decimal` (NaN, sNaN, Infinity); an integer outside ±(2^53 − 1); bytes; strings containing a surrogate code point (U+D800 to U+DFFF), which cannot be encoded as UTF-8; non-string mapping keys; duplicate keys; subclasses and enums; `set` and `frozenset`; and strategy-defined classes. Mutable containers are copied, never kept.

## Consequences

- **Limitation (OD-21).** A strategy that needs data of another instrument, whether as market context (for example a reference index or a correlated asset) or to relate two instruments (for example a spread), cannot be expressed. This is recorded as open decision **OD-22**, not rejected.
- **Possible future extension (OD-22, not decided).** One shape that keeps OD-21 intact: an evaluation keeps its single primary instrument and its state scope, and may additionally receive read-only **context series** of other instruments that the strategy declares. Those series would be built at the same `as_of` by the same snapshot builder under the same availability and validation rules as the primary instrument's (DR-01 to DR-07, DR-15, DR-16, DR-20, DR-21, DR-24), so a context series could never be fresher than the primary data allows. What it would still need decided: how context instruments are declared (OD-13) and drawn from the universe (OD-4); whether a missing or failing context series fails the whole evaluation (DR-14, OD-8); whether the state scope must include the set of context instruments (DR-27, OD-17); and how strategies sharing context relate to OD-15. It relies on OD-6 and OD-7 for every input it reads and does not answer them.
- Instrument identity itself stays open (OD-4).
- Still open in OD-3: the taxonomy of failure codes and whether a result carries evidence. Taxonomy is expected with the data-quality gate (SE-6).
- Still open in OD-13: how a strategy declares the inputs it needs (expected with SE-5) and where strategy specifications live.
- Payloads may nest without a depth or size bound. Integers are bounded to ±(2^53 − 1), so a consumer that parses JSON numbers as binary doubles, such as JavaScript's `JSON.parse`, still reads every integer exactly; a `Decimal` is text and never read as a number. Signals are expected to reach a database, a frontend and notifications (given by the user, 2026-11-10; delivery itself stays OD-11). If a depth or size bound is needed (for example for storage, OD-20 or OD-11), it is a new decision.
- **SE-1 implements the canonical form**, because payload equality is defined by it. Whether the encoder uses the standard library's `json` module (which would join the pure-layer allowlist, `CLAUDE.md`) or is written by hand is left to the SE-1 plan; either must reproduce the test vectors byte for byte.
- Implementation obligations of SE-1, not further decisions: in Python `True == 1` and `Decimal("1.0") == Decimal("1.00")` hold, so payload equality must use the canonical form, never Python equality of raw values; construction must match kinds by exact type (`type(x) is int`, not `isinstance`, which also accepts `bool` and enums), reject every value listed under "What is not a payload value", and copy nested containers into frozen form so that no payload can be mutated after construction; the `Decimal` text must be produced without reading the current `decimal` context.
