# SE-6 Quasar REST Client Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task by task. Steps use checkbox (`- [ ]`) syntax for tracking. In this project the lifecycle is `/slice SE-6` (`.claude/skills/slice/SKILL.md`), and its rules override the sub-skill.

**Goal:** A transport-only, standard-library client for `GET /v1/candles`, `GET /v1/open-interest` and `GET /v1/funding-rates` that reads a whole explicit window page by page, checks every response against the Quasar contract, parses decimals exactly, and returns the pages separately as immutable values holding SE-3 rows; anything else is a typed client error.

**Architecture:** One package, `sentaris_engine.infrastructure.quasar`. Task 1 adds the errors, the page types, the response value and the strict JSON body layer (no `float`, no ambiguous JSON). Task 2 adds the three single-page decoders (spec 5.4) with the contract fixtures. Task 3 adds `QuasarClient`: argument checks, request URLs, paging and status mapping over an injected transport. Task 4 adds the default urllib transport.

**Tech Stack:** Python 3.12, stdlib only (`urllib.request`, `urllib.parse`, `urllib.error`, `http.client`, `json`, `re`, `decimal`, `dataclasses`, `typing`); pytest, mypy strict, ruff, import-linter as set up in SE-1.

**Spec:** `docs/superpowers/specs/2026-11-13-se-6-quasar-rest-client-design.md` (revision 5, approved). "Spec 5.4", "U3" below refer to that document. The domain document is `docs/domain.md`; the Quasar contract is `../quasar-market-data/docs/contracts/api-v1.md` ("contract 6.7.3").

**Status:** Revision 2, approved by the user (2026-11-13).

**Revision:** 2. Revision 1 was reviewed by Opus (`slice-reviewer`: approved with changes; 0 CRITICAL, 1 HIGH, 5 MEDIUM, 11 LOW; none needed a domain decision). Revision 2 applies the user's two corrections on the `base_url` port (Task 3), fixes HIGH-1 (with spec revision 5, approved by the user), all MEDIUM and LOW-1 to LOW-9. LOW-10 (merge Tasks 3 and 4) and LOW-11 (extra contract-consistency checks) are not taken, at the user's instruction to keep the four-task structure and add no scope.

## Global Constraints

- No dependency is added (`[project].dependencies` stays `[]`) and no list in `tests/architecture/` changes (AC-10). `infrastructure` is not pure; it may import any stdlib module and `sentaris_engine.domain`, never `application` or `strategies` (import-linter).
- **No `float`** anywhere in the package except the one `timeout_ms / 1000` at the urllib call in Task 4 (spec 5.6, DR-11). Prices are built only by `Decimal(text)` from a string that passed the canonical regex.
- **Exact types.** Every type check of a decoded JSON value or an argument uses `type(v) is X` (so `bool` is never an `int`, a `str` subclass is never a `str`). `isinstance` only where the stdlib forces it.
- **No broad handlers.** No `except Exception`, no bare `except`, no `except BaseException`. Each `try` names exactly the exceptions spec 5.4 or 5.6 lists, around exactly the call spec 5.4 or 5.6 names. Translations chain the original (`raise ... from exc`).
- **Value types** follow SE-3: `@final`, `@dataclass(frozen=True, slots=True)`, checks in `__post_init__`, `__init_subclass__` raising `TypeError`. A malformed field of a page type or of `HttpResponse` raises exactly `TypeError` (wrong type) or `ValueError` (wrong value); these are construction errors of infrastructure values, not `EvaluationTypeError` (R4).
- **Nothing from the environment or the clock**: no `os.environ`, no `time`, no `random`, no logging of bodies.
- **Tests** assert exception classes exactly with `raises_exactly` from `tests/domain/evaluation_helpers.py` (or `pytest.raises` plus `type(info.value) is X`), never messages. Chained causes are asserted with `type(exc.__cause__) is ...`. Each test named in spec section 8 is its own test function; tests that share cases share a module-level case list.
- **Fixtures** are the contract's own examples or hand-written from it; negative cases derive from a valid fixture by exactly one edit (spec section 8).
- **Comments** cite rules by ID (DR-11, DR-15, OD-24, U2, contract 6.7.3); they do not restate them.
- **Documents.** `docs/domain.md` and `docs/roadmap.md` do not change. `CLAUDE.md` changes only in Task 4 ("Current state").
- **Local sockets.** Task 4's tests bind `127.0.0.1` on port 0. If the sandbox refuses the bind, the orchestrator reruns `make check` outside the sandbox and records that in the report; the tests are never skipped or weakened.

## Rulings made in this plan (implementation only)

- **R1. Module layout** (file structure table). `__init__.py` re-exports the public names: `QuasarClient`, `HttpResponse`, `Transport`, `urllib_transport`, the four page types, the four error classes.
- **R2. The JSON layer is split** into `parse_json(body: bytes) -> object`, which raises the spec 5.4 exceptions untranslated, and two callers: `decode_ok_body` (translates them into `QuasarProtocolError`) and `error_fields` (turns them into `None`). `PARSE_FAILURES` is the one tuple of the 5.4 table, used by both callers, so the 200 path and the non-200 predicate cannot drift.
- **R3. The hooks are module-level functions** (`_parse_float`, `_parse_int`, `_parse_constant`, `_object_pairs`) that `parse_json` reads from the module globals at each call, so a test can replace one with `monkeypatch.setattr` (spec 8, `test_hook_programming_error_propagates`).
- **R4. Construction errors of infrastructure values** (`HttpResponse`, page types, client arguments) are plain `TypeError`/`ValueError`. Exception: time arguments and `timeout_ms` are checked with SE-3's `check_instant`/`check_duration`, whose `EvaluationTypeError` (a `ValueError`) propagates unchanged (spec 5.1, 5.2 "checked with"). Per argument the exact class is fixed in Task 3.
- **R5. Inside the decoders, instants are checked against `MAX_TIME_MS`** from `sentaris_engine.domain.timing` with the same predicate as `check_instant` (`type(v) is int and 0 <= v <= MAX_TIME_MS`), raising `QuasarProtocolError` directly; `check_instant` is not called inside a `try` there, because spec 5.4 allows exactly one translation on the parsed tree (the row constructor's).
- **R6. Content-Type parsing** (spec 5.4 "Body"): split on `;`; the first part, stripped of spaces and tabs and lower-cased, must equal `application/json`; every further non-empty part is `name=value` (a part without `=` is ignored, as an unknown parameter); a part whose stripped, lower-cased name is `charset` must have a value that, stripped and with one pair of surrounding `"` removed, lower-cases to `utf-8`. Every `charset` part is checked.
- **R7. `base_url`** must consist only of characters `!` to `~` (no space, no control, no non-ASCII), parse with `urllib.parse.urlsplit` to scheme `http` or `https`, a non-empty `hostname`, a `port` that the `.port` attribute of the `urlsplit` result accepts (it is read explicitly; its `ValueError` for a non-numeric or out-of-range port propagates; Task 3), no `@` in the netloc, and contain no `?`, `#` or `;`. All trailing `/` of the path are removed, not only one (a slight widening of spec 5.1's "a trailing `/` is ignored": `/q//` becomes `/q`); the endpoint path is appended to what remains.
- **R8. `HttpResponse` checks its fields**: `status` exact `int`, `content_type` exact `str` or `None`, `body` exact `bytes`. The client additionally checks `type(result) is HttpResponse` for an injected transport's return and raises `TypeError` otherwise (a broken transport is a programming error; spec 5.1).
- **R9. Decoders do not look at `status`**; the client calls them only for `200`.

## Review Focus

1. **Content-Type spellings:** `Application/JSON; Charset="UTF-8"`, `application/json;charset=utf-8`, `application/json ; foo=bar` and `application/json;` are accepted; `application/jsonx`, `application/json-seq`, `text/json`, `application/json; charset=latin-1` and `application/json; charset=utf-8; charset=latin-1` are refused (R6). Test `test_content_type_spellings` (Task 1).
2. **Identifiers with reserved and non-ASCII characters:** `symbol="BTC/USDT:USDT"` is sent unencoded; `symbol="Ä B+%&#"` is sent as `%C3%84%20B%2B%25%26%23`, and a response echoing `"Ä B+%&#"` (the decoded text) is accepted. Test `test_identifiers_are_encoded_and_echo_compared_decoded` (Task 3).
3. **`base_url` with a path prefix:** `http://127.0.0.1:8080/quasar/` and `http://127.0.0.1:8080/quasar` both give `http://127.0.0.1:8080/quasar/v1/candles?...`; `https://h` gives `https://h/v1/candles?...`; `http://[::1]:9/` is accepted. Test `test_base_url_forms` (Task 3).
4. **Small decimals and `str`:** `"0.00000001"` decodes to a `Decimal` with `str` `1E-8`; exactness is asserted with `format(value, "f") == text` and `value.as_tuple().exponent`, never with `str`, and the decoder never normalises or quantises to make `str` match (spec behavior 4, revision 5; DR-11, DR-17). Test `test_decimal_text_is_exact` (Task 2).
5. **A later page echoes the cursor, not the caller's `start`:** in a two-page read, a second response that echoes the caller's original `start` instead of the first page's `next` is a `QuasarProtocolError`, and nothing is returned. Test `test_later_page_must_echo_cursor` (Task 3).
6. **An error response whose body cannot be read:** a `500` that announces `Content-Length: 100`, sends 10 bytes and closes is a `QuasarTransportError` with cause `http.client.IncompleteRead`, not a bare `HTTPException` (spec 5.6). Case of `test_transport_failure_is_transport_error` (Task 4).

Also covered: a full final page with `next: null` (`len(rows) == limit`) is accepted (Task 2, `test_full_last_page_with_null_next_is_accepted`); `conflicted` as `0` or `1` is refused by the decoder itself, with `__cause__ is None` (Task 2, `test_wrong_json_type_is_refused`).

---

## File structure

| File | Task | Responsibility |
|---|---|---|
| `src/sentaris_engine/infrastructure/quasar/__init__.py` | 1, 3, 4 | Public re-exports (R1); each task adds its names. |
| `src/sentaris_engine/infrastructure/quasar/errors.py` | 1 | `QuasarClientError`, `QuasarTransportError`, `QuasarResponseError`, `QuasarProtocolError`. |
| `src/sentaris_engine/infrastructure/quasar/pages.py` | 1 | `SeriesBounds`, `CandlePage`, `OpenInterestPage`, `FundingRatePage`. |
| `src/sentaris_engine/infrastructure/quasar/transport.py` | 1, 4 | Task 1: `HttpResponse`, `Transport`. Task 4: `urllib_transport`. |
| `src/sentaris_engine/infrastructure/quasar/body.py` | 1 | `JsonFraction`, hooks, `PARSE_FAILURES`, `parse_json`, `decode_ok_body`, `error_fields`. |
| `src/sentaris_engine/infrastructure/quasar/decoding.py` | 2 | `decode_candle_page`, `decode_open_interest_page`, `decode_funding_rate_page`. |
| `src/sentaris_engine/infrastructure/quasar/client.py` | 3 | `QuasarClient`. |
| `tests/infrastructure/__init__.py` | 1 | Package marker. |
| `tests/infrastructure/test_body.py` | 1 | Errors, page types, `HttpResponse`, JSON layer, error predicate. |
| `tests/infrastructure/fixtures/*.json` | 2 | Contract examples and hand-written bodies (below). |
| `tests/infrastructure/quasar_bodies.py` | 2 | Body index, request of each body, and body editing helpers. |
| `tests/infrastructure/test_decoding.py` | 2 | Spec 5.4 checks per page; AC-3, AC-4, AC-5, AC-9. |
| `tests/infrastructure/quasar_fakes.py` | 3 | `FakeTransport`, `ok(...)`, `error(...)`. |
| `tests/infrastructure/test_client.py` | 3 | AC-1, AC-2, AC-6, AC-8, behavior 1 to 9 over the fake transport. |
| `tests/infrastructure/local_server.py` | 4 | Threaded `127.0.0.1` HTTP server fixture with scripted handlers and a request log. |
| `tests/infrastructure/test_transport.py` | 4 | AC-7 and the default-transport part of 5.5. |
| `CLAUDE.md` | 4 | "Current state": SE-6 exists. |

## Interfaces (whole slice)

```python
# errors.py
class QuasarClientError(Exception): ...
class QuasarTransportError(QuasarClientError): ...
class QuasarResponseError(QuasarClientError):
    status: int; code: str | None; reason: str | None
    def __init__(self, status: int, code: str | None, reason: str | None) -> None: ...
class QuasarProtocolError(QuasarClientError): ...

# pages.py  (all @final frozen slots dataclasses, R4 checks)
SeriesBounds(oldest: int, newest: int)                          # instants (R5 predicate), oldest <= newest
CandlePage(start: int, end: int, series: SeriesBounds, rows: tuple[Candle, ...], next: int | None)
OpenInterestPage(start: int, end: int, series: SeriesBounds, rows: tuple[OpenInterest, ...], next: int | None)
FundingRatePage(start: int, end_inclusive: int, series: SeriesBounds | None, rows: tuple[FundingRate, ...], next: int | None)

# transport.py
HttpResponse(status: int, content_type: str | None, body: bytes)  # @final frozen slots, R8
type Transport = Callable[[str, int], HttpResponse]
def urllib_transport(url: str, timeout_ms: int) -> HttpResponse: ...  # Task 4

# body.py
@final class JsonFraction:  text: str        # marker for a JSON number with fraction/exponent; not int, str, float
PARSE_FAILURES: tuple[type[Exception], ...]  # (UnicodeDecodeError, json.JSONDecodeError, RecursionError, _JsonRefused)
def parse_json(body: bytes) -> object: ...
def decode_ok_body(content_type: str | None, body: bytes) -> dict[str, object]: ...  # Content-Type, parse, top-level object
def error_fields(status: int, body: bytes) -> tuple[str | None, str | None]: ...    # (code, reason), spec 5.5 predicate

# decoding.py  (R9; raise QuasarProtocolError)
def decode_candle_page(response: HttpResponse, venue: str, symbol: str, timeframe: str,
                       start: int, end: int, limit: int | None) -> CandlePage: ...
def decode_open_interest_page(response: HttpResponse, venue: str, symbol: str, period: str,
                              start: int, end: int, limit: int | None) -> OpenInterestPage: ...
def decode_funding_rate_page(response: HttpResponse, venue: str, symbol: str,
                             start: int, end_inclusive: int, limit: int | None) -> FundingRatePage: ...

# client.py
class QuasarClient:  # @final
    def __init__(self, base_url: str, timeout_ms: int, transport: Transport | None = None) -> None: ...
    def read_candles(self, venue: str, symbol: str, timeframe: str, start: int, end: int,
                     limit: int | None = None) -> tuple[CandlePage, ...]: ...
    def read_open_interest(self, venue: str, symbol: str, period: str, start: int, end: int,
                           limit: int | None = None) -> tuple[OpenInterestPage, ...]: ...
    def read_funding_rates(self, venue: str, symbol: str, start: int, end_inclusive: int,
                           limit: int | None = None) -> tuple[FundingRatePage, ...]: ...
```

---

### Task 1: Errors, page types, response value and the strict JSON layer

**Implementer:** `opus`. The JSON layer carries DR-11 (no `float` while decoding, ignored fields included) and the exact exception list of spec 5.4 (U5); a too-broad `except`, a `ValueError` caught around `json.loads`, or `json.loads(bytes)` (encoding detection) passes ordinary tests and breaks the spec (slice skill, rule 4).

**Files:** the Task 1 rows of the file structure table.

**Scope:** spec 5.3, 5.4 "Body" and its exception table, 5.5 (classes and the `code`/`reason` predicate), R2, R3, R6, R8.

**Interfaces:** consumes `Candle`, `OpenInterest`, `FundingRate`, `MAX_TIME_MS`; produces everything listed under errors.py, pages.py, `HttpResponse`/`Transport` and body.py above.

- [ ] **Step 1: Write the failing tests in `tests/infrastructure/test_body.py`**

  - `test_error_classes`: the three kinds are distinct direct subclasses of `QuasarClientError`, which subclasses `Exception` and not `EvaluationTypeError`; `QuasarResponseError(503, "not_ready", "database_missing")` carries the three attributes as given.
  - `test_page_types_are_validated_final_and_frozen`: `SeriesBounds(True, 1)` and `SeriesBounds(1.0, 2)` → `TypeError`; `SeriesBounds(-1, 0)`, `SeriesBounds(0, 2**53)` and `SeriesBounds(5, 4)` → `ValueError`; `CandlePage` with `rows` as a `list`, a tuple holding an `OpenInterest`, `series=None`, `next=True`, `start="1"` → `TypeError`, `next=-1` → `ValueError`; `FundingRatePage(..., series=None, ...)` is accepted; subclassing any page type raises `TypeError`; field assignment raises `FrozenInstanceError`; equal fields compare equal.
  - `test_http_response_is_validated`: `status` `"200"`/`True`, `content_type` `b"x"`, `body` `bytearray(b"")`/`"x"` raise exactly `TypeError`; `HttpResponse(200, None, b"")` is accepted.
  - `test_json_number_with_fraction_becomes_marker`: `parse_json(b'{"a": 82709.5, "b": 8.27E4, "c": [1e3]}')` gives `JsonFraction` instances with `text` `"82709.5"`, `"8.27E4"`, `"1e3"`; `JsonFraction` is no `int`, `str`, `float` or `Decimal` (`issubclass` false for each).
  - `test_no_float_is_built_for_ignored_fields`: for the contract 5.2 example body (inline bytes here) with `"coverage": {"x": [{"y": 0.5}]}` and an unknown top-level `"z": -1.25E-3`, a recursive walk of `parse_json(body)` over dicts and lists finds no `float` at any depth and exactly two `JsonFraction` values; with `monkeypatch.setattr(body, "_parse_float", float)` the same walk finds a `float` (proves the walk would catch a regression).
  - `test_parse_failures_are_protocol_errors` (one case per row of the 5.4 table): `decode_ok_body("application/json", b)` raises exactly `QuasarProtocolError`, and `type(exc.__cause__)` is: `UnicodeDecodeError` for `b'{"a":"\xff"}'`; `json.JSONDecodeError` for `b'{'`, `b''`, `b'{} {}'` and `b'\xef\xbb\xbf{}'` (BOM); `RecursionError` for `b'[' * 200_000`; the private refusal error for `b'{"a": NaN}'`, `b'{"a": [Infinity]}'`, `b'{"a": -Infinity}'`, `b'{"a": 1, "a": 1}'`, `b'{"x": {"b": 1, "b": 2}}'` and `b'{"a": ' + b"1" * 5000 + b'}'`.
  - `test_invalid_utf8_body_is_refused`: the `UnicodeDecodeError` case above, as its own function over the shared case list.
  - `test_oversized_integer_and_deep_nesting_are_protocol_errors`: the 5000-digit and the `RecursionError` cases, as their own function. Wherever the 5000-digit case runs (here and in `test_parse_failures_are_protocol_errors`), one shared context manager or fixture sets `sys.set_int_max_str_digits(4300)` and restores the previous `sys.get_int_max_str_digits()` in `finally`, so neither test does not depend on `PYTHONINTMAXSTRDIGITS` or `-X int_max_str_digits` (the client's behavior does: spec 5.4 uses Python's limit; recorded as a known limitation in the slice report).
  - `test_utf16_body_is_refused`: `'{}'.encode("utf-16")` and `'{}'.encode("utf-32")` → `QuasarProtocolError`.
  - `test_top_level_not_object_is_refused`: `b'[]'`, `b'"x"'`, `b'1'`, `b'null'` → `QuasarProtocolError` (raised directly; `__cause__ is None`).
  - `test_non_json_content_type_is_refused` (`None`, `"text/plain"`, `""`) and `test_non_utf8_charset_is_refused` (`"application/json; charset=latin-1"`) → `QuasarProtocolError`; plus Review Focus 1 as `test_content_type_spellings`.
  - `test_hook_programming_error_propagates`: for each of `_parse_constant`, `_object_pairs`, `_parse_int`, `_parse_float`, monkeypatch the hook with one raising `RuntimeError`, feed a body that reaches it, and assert the `RuntimeError` reaches the caller of `decode_ok_body` unchanged (`type(...) is RuntimeError`).
  - `test_error_body_shapes` (spec 5.5 predicate): `error_fields(400, <contract section 2 body>) == ("invalid_parameter", None)`; `error_fields(503, b'{"error":{"code":"not_ready","message":"m","details":{"reason":"database_missing"}}}') == ("not_ready", "database_missing")`; `code` and `reason` are `None` for: a non-JSON body, `b''`, invalid UTF-8, a NaN body, a duplicate-key body, a top-level array, no `error`, `error` not an object, `code` `1`/`""`/`null`/missing; `reason` is `None` (with the code kept) for 503 `not_ready` with no `details`, `details` an array, `reason` `1`, and for `status` 500 or `code` `"other"` with a `reason` present. `error_fields` never raises for any of these.

- [ ] **Step 2: Run the tests and see them fail (RED)**

  Run: `uv run pytest tests/infrastructure -q`
  Expected: collection error, `sentaris_engine.infrastructure.quasar` does not exist.

- [ ] **Step 3: Implement errors.py, pages.py, the Task 1 part of transport.py, body.py and `__init__.py`**

  `parse_json` is exactly: `text = body.decode("utf-8")` (strict, no BOM handling), then one `json.loads(text, parse_float=_parse_float, parse_int=_parse_int, parse_constant=_parse_constant, object_pairs_hook=_object_pairs)` with the hooks read from module globals at the call (R3). `_parse_int` converts with `int(text)` inside a `try` that turns only that call's `ValueError` into `_JsonRefused`; `_parse_constant` always raises `_JsonRefused`; `_object_pairs` raises `_JsonRefused` on a repeated key, else returns a `dict`. `_JsonRefused` is a private `Exception` subclass. `decode_ok_body` checks Content-Type (R6), then `try: tree = parse_json(body) except PARSE_FAILURES as exc: raise QuasarProtocolError(...) from exc`, then the top-level object. `error_fields` uses the same `except PARSE_FAILURES` and returns `(None, None)` there. Page types check with the R5 predicate and `type(...) is` for every element of `rows`.

- [ ] **Step 4: Run the tests and see them pass (GREEN)**

  Run: `uv run pytest tests/infrastructure -q && uv run mypy src/sentaris_engine/infrastructure tests/infrastructure`. Expected: all pass, mypy clean.

- [ ] **Step 5: Run the gate and commit**

  Run: `make check`. Expected: every step clean; the last pytest line reports `passed`, no failures.

  ```bash
  git add src/sentaris_engine/infrastructure/quasar tests/infrastructure docs/superpowers/specs/2026-11-13-se-6-quasar-rest-client-design.md docs/superpowers/plans/2026-11-13-se-6-quasar-rest-client.md
  git commit -m "feat: SE-6 Quasar errors, page types and strict JSON body"
  ```

**Completion condition:** the Task 1 tests pass; `make check` passes.

---

### Task 2: Single-page decoders and the contract fixtures

**Implementer:** `opus`. Spec 5.4 is the bulk of the slice's guarantees: canonical decimal text (`re.fullmatch`, ASCII `[0-9]`, `-0`), no defaults for missing or `null` fields (DR-15), exact window and `next` bounds that differ between exclusive and inclusive ends. Off-by-one and `re.match`/`\d` mistakes pass the positive tests (slice skill, rule 4).

**Files:** the Task 2 rows of the file structure table.

**Scope:** spec 5.4 "Echoed fields", "Series", "Rows", "Order and window", "`next`"; AC-3, AC-4, AC-5, AC-9; behavior 3 to 6.

**Interfaces:**
- Consumes Task 1 (`decode_ok_body`, `JsonFraction`, page types, `HttpResponse`, `QuasarProtocolError`), `Candle`, `OpenInterest`, `FundingRate`, `EvaluationTypeError`, `MAX_TIME_MS`.
- Produces the three decoders (interfaces block). Each public decoder passes the module-global row class (`Candle`, `OpenInterest` or `FundingRate`) to the shared core at call time, read from the module globals at each call as R3 does for the hooks, so `monkeypatch.setattr(decoding, "Candle", ...)` takes effect; no table binds a row class at import time. In `tests/infrastructure/quasar_bodies.py`:
  - `BODIES: dict[str, str]`: body name → the contract section it follows (for example `"candles_example": "contract 5.2"`); every file in `fixtures/` has an entry and vice versa (asserted by `test_body_index_is_complete`);
  - `REQUESTS: dict[str, Request]` for every `200` body, where `Request` is a frozen dataclass `Request(endpoint: Literal["candles", "open_interest", "funding"], venue: str, symbol: str, series: str | None, start: int, end: int, limit: int | None)` (`series` is the timeframe or period, `None` for funding; `end` is `end_inclusive` for funding): the request that body answers;
  - `load(name: str) -> bytes`: the file's bytes;
  - `decode(name: str, body: bytes | None = None) -> CandlePage | OpenInterestPage | FundingRatePage`: runs the matching decoder with `REQUESTS[name]` on `body` (default `load(name)`);
  - `class Raw:` holding JSON text to splice in verbatim; `DELETE`: a sentinel;
  - `edited(name: str, path: tuple[str | int, ...], value: object) -> bytes`: the body with one value replaced or added (`Raw` spliced verbatim, `DELETE` removes the key), serialised with `json.dumps(..., ensure_ascii=False).encode()`.

  **Bodies** (`tests/infrastructure/fixtures/`): `candles_example.json`, `open_interest_example.json`, `funding_example.json` (contract 5.2, 6.5.4, 6.7.4, verbatim, byte for byte from the code blocks); `candles_paged_{1,2,3}.json` (limit 2: 2, 2, 1 rows, with a gap between pages 1 and 2 so `next` is not `last + 300000`); `open_interest_paged_{1,2}.json` (limit 2: 2, 1 rows); `funding_paged_{1,2}.json` (contract 6.7.3: `limit` 3, rows `t1 Regular`, `t2 Regular` on page 1 with `next = t3`, because `t3 Regular` and `t3 Special` may not be split; page 2 starts at `t3` with both); `candles_empty.json` (an existing series, `candles: []`, `next: null`); `funding_series_null.json` (`series: {"oldest_funding_time_ms": null, "newest_funding_time_ms": null}`, `rows: []`); `error_400_invalid_parameter.json`, `error_404_unknown_series.json`, `error_404_not_found.json`, `error_405_method_not_allowed.json`, `error_500_internal_error.json`, `error_503_not_ready.json` (contract section 2; the 503 with `reason` `database_missing`). Each paged and edge body keeps `coverage`, `as_of_ms`, `rule` blocks shaped as in the contract so AC-9 is exercised on every read. The request each `200` body answers is its `REQUESTS` entry.

- [ ] **Step 1: Write the failing tests in `tests/infrastructure/test_decoding.py`**

  Each test that applies to more than one endpoint is parametrised over the endpoints (spec 8). Valid requests are those of the fixture.

  - `test_body_index_is_complete`: the set of files in `fixtures/` equals `set(BODIES)` (with `.json`), and every `200` body has a `REQUESTS` entry.
  - `test_contract_examples_decode` (AC-3): the three examples decode field by field into the expected page: for 5.2 with `limit=3` and `end=1792673400000`, `next == 1792644300000`, the second row `close == Decimal("82709")`, `series == SeriesBounds(1792643400000, 1792673100000)`; for 6.5.4 the second row has `conflicted is True`; for 6.7.4 the fourth row is `Special` at `1792713600650` and `funding_rate` of the second is `Decimal("-0.00005123")`. Every `Decimal` field satisfies `format(value, "f") == <body text>`.
  - `test_decimal_text_is_exact` (behavior 4, spec revision 5; Review Focus 4): `"0.00000001"` and `"12345678901234567890.123456789"` in a price and `"-0.00005123"` in `funding_rate` give `Decimal`s with `format(value, "f") == text` and `value.as_tuple().exponent == -(digits after the ".")` (`-8`, `-9`, `-8`); for `"0.00000001"` the test also asserts `str(value) == "1E-8"`, documenting that `str` is not the check.
  - `test_nullable_fields` (behavior 5): `turnover: null`, `mark_price: null` → `None`; the key deleted → `QuasarProtocolError`.
  - `test_unknown_fields_are_ignored` (AC-9, AC-5): extra keys at top level, in `series`, in a row, in `coverage`, and `coverage`/`as_of_ms`/`rule` replaced by `Raw('"garbage"')` all decode to the same page as the unedited body; so do `Raw("0.5")` inside `coverage`, an unknown top-level key with `Raw("-1.25E-3")` and an unknown row key with `Raw("1e3")` (a fraction marker in an ignored field is ignored, spec 5.4).
  - `test_empty_page` (behavior 3) and `test_funding_series_null` decode with `rows == ()`, `next is None`.
  - `test_json_number_with_fraction_is_refused` (DR-11): a price as `Raw("82709.5")` and `Raw("8.27E4")`, `open_time_ms` as `Raw("1.7926434E12")`, `next` and a series bound as `Raw("1.5")`.
  - `test_nan_and_infinity_are_refused`: `Raw("NaN")` as a price and inside `coverage`.
  - `test_duplicate_json_key_is_refused`: a repeated `venue` (text edit on the fixture bytes), and `Raw('{"a":1,"a":2}')` inside `coverage`.
  - `test_non_canonical_decimal_is_refused`: the spec 8 list, each in `open` (and `funding_rate` where signed: `"-0"`, `"+1"`); `"-1"` in a price; `"-0.5"` accepted for `funding_rate`, refused for `mark_price`.
  - `test_missing_row_field_is_refused` and `test_null_in_non_nullable_field_is_refused`: every documented row field of the 5.4 table in turn.
  - `test_wrong_json_type_is_refused`: `true` and `"1792643400000"` for an integer, `82709` (integer) for a decimal string, `"false"`, `0`, `1` for `conflicted`, `1` for `rate_type`. Every case asserts `__cause__ is None`: the decoder refuses the JSON type itself, not the SE-3 row constructor.
  - `test_unknown_rate_type_is_refused`: `"regular"`, `"Other"`, `""`.
  - `test_instant_out_of_range_is_refused`: `-1` and `2**53` in a row time, a series bound and `next`.
  - `test_missing_echoed_field_is_refused`, `test_echoed_identifier_mismatch_is_refused` (also a non-`str` echo), `test_echoed_window_mismatch_is_refused` (`start` and `end` off by one), `test_wrong_time_semantics_is_refused` (open interest and funding: missing, `"period_start"`, `null`), `test_missing_rows_key_is_refused`, `test_missing_next_is_refused`, `test_missing_series_is_refused`.
  - `test_series_not_object_is_refused`, `test_series_field_missing_null_or_wrong_type_is_refused`, `test_series_bounds_inverted_is_refused`, `test_funding_series_half_null_is_refused`.
  - `test_rows_not_array_is_refused`, `test_row_not_object_is_refused`, `test_rows_not_ascending_are_refused` (funding: `Special` before `Regular` at one time), `test_duplicate_row_key_is_refused`.
  - `test_row_outside_window_is_refused`: a row at `start - 1`; a candle or open interest row at `end`; a funding row at `end_inclusive + 1`. Positive: a candle/open interest row at `end - 1` and a funding row at `end_inclusive` are accepted.
  - `test_more_rows_than_limit_are_refused`: a fixture with `limit` one less than its row count; and a 1001-row page with `limit=None` (generated in the test). `test_full_last_page_with_null_next_is_accepted`: `len(rows) == limit` with `next: null`.
  - `test_next_wrong_type_is_refused` (`"1"`, `true`, `Raw("1.5")`), `test_next_not_after_last_row_is_refused` (`next == last`, `next < last`), `test_next_outside_window_is_refused` (candle/open interest `next == end`, funding `next == end_inclusive + 1`; positive: funding `next == end_inclusive`), `test_next_with_no_rows_is_refused`.
  - `test_row_constructor_refusal_is_protocol_error`: `monkeypatch.setattr(decoding, "Candle", <callable raising EvaluationTypeError>)` (effective because of the call-time lookup under Interfaces); the decoder raises `QuasarProtocolError` with `type(__cause__) is EvaluationTypeError`.

- [ ] **Step 2: Run the tests and see them fail (RED)**

  Run: `uv run pytest tests/infrastructure/test_decoding.py -q`
  Expected: collection error, `decoding` does not exist.

- [ ] **Step 3: Implement `decoding.py` and the fixtures**

  Decimals: `_UNSIGNED = re.compile(r"(0|[1-9][0-9]*)(\.[0-9]*[1-9])?")`, matched with `fullmatch` on an exact `str`; signed is an optional leading `-` before the same pattern, with `"-0"` refused; then `Decimal(text)`. One shared core for the three endpoints is expected (field names and window kind as parameters); the endpoint differences are exactly those of spec 5.4: rows key, time field, sort key, inclusive or exclusive end, nullable `series`, `time_semantics`. The only `try` in the module wraps the row constructor call and catches exactly `EvaluationTypeError` (spec 5.4).

- [ ] **Step 4: Run the tests and see them pass (GREEN)**

  Run: `uv run pytest tests/infrastructure -q`. Expected: all pass.

- [ ] **Step 5: Run the gate and commit**

  Run: `make check`. Expected: clean, `passed`.

  ```bash
  git add src/sentaris_engine/infrastructure/quasar tests/infrastructure
  git commit -m "feat: SE-6 Quasar page decoders and contract fixtures"
  ```

**Completion condition:** AC-3, AC-4 (checks of 5.4 beyond the body layer), AC-5, AC-9 hold; `make check` passes.

---

### Task 3: The client: arguments, request URLs, paging and status mapping

**Implementer:** `sonnet`. With the decoders done, this is argument checking, URL building and a loop, each pinned by spec 5.1, 5.2 and 5.5 and the rulings above.

**Files:** the Task 3 rows of the file structure table; `__init__.py` gains `QuasarClient`.

**Scope:** spec 5.1, 5.2, 5.5 (mapping, no partial result), behavior 1, 2, 7, 8 (injected part), 9; AC-1, AC-2, AC-6, AC-8; Review Focus 2, 3, 5.

**Interfaces:**
- Consumes Tasks 1 and 2, `check_instant`, `check_duration`, and `tests/infrastructure/quasar_bodies.py`.
- Produces `QuasarClient` (interfaces block), and in `tests/infrastructure/quasar_fakes.py`: `FakeTransport(responses: list[HttpResponse | BaseException])`, a callable that records `calls: list[tuple[str, int]]`, returns or raises the next item, and fails the test (`AssertionError`) when called once too often (the R8 cases, which return a non-`HttpResponse`, use a plain lambda transport instead); `ok(body: bytes) -> HttpResponse` (`200`, `"application/json; charset=utf-8"`); `error(status: int, body: bytes, content_type: str | None = "application/json; charset=utf-8") -> HttpResponse`.

  `QuasarClient` stores the normalised base, `timeout_ms` and the transport (`transport.urllib_transport` when `None`). Task 3 adds `urllib_transport` to `transport.py` as a stub with the final signature that raises `NotImplementedError`; Task 4 replaces its body. No Task 3 test calls it. Request URL: `base + path + "?" + "&".join(f"{name}={quote(value, safe='/:')}")` in the fixed order `venue, symbol, timeframe|period, start, end[, limit]`. Each read: check arguments (all before the first call), then loop: call the transport with `(url, timeout_ms)`, check `type(result) is HttpResponse` (R8), `status != 200` → `QuasarResponseError(status, *error_fields(status, body))`, else decode with the cursor as `start`; append; continue with `start = page.next` while it is not `None`; return `tuple(pages)`.

  Argument errors (R4): an identifier not exact `str` → `TypeError`; empty, or failing `value.encode("utf-8")` (raise `ValueError` from `None`) → `ValueError`; `start`/`end`/`end_inclusive` → whatever `check_instant` raises (`EvaluationTypeError`); `limit` not `None` and not exact `int` → `TypeError`, below 1 → `ValueError`; `base_url` not exact `str` → `TypeError`, otherwise R7 → `ValueError`. The constructor must read `urllib.parse.urlsplit(base_url).port` explicitly (the attribute access is what validates it; `urlsplit` alone does not), so a numeric port outside `0`–`65535` and a non-numeric port both raise `ValueError` in `QuasarClient(...)`, before any transport call; `timeout_ms` → `check_duration`'s `EvaluationTypeError`; `transport` neither `None` nor callable → `TypeError`.

- [ ] **Step 1: Write the failing tests in `tests/infrastructure/test_client.py`**

  - `test_request_urls` (AC-1): for each operation, with `base_url="http://q.test:8080"`, the URL is exactly e.g. `http://q.test:8080/v1/candles?venue=binance-usdm&symbol=BTC/USDT:USDT&timeframe=5m&start=1792643400000&end=1792673400000&limit=3`; without `limit` the parameter is absent; funding has no `timeframe`/`period` and sends `end_inclusive` as `end`; the timeout passed is the configured `timeout_ms`.
  - `test_identifiers_are_encoded_and_echo_compared_decoded` (Review Focus 2), `test_base_url_forms` (Review Focus 3).
  - `test_single_page_read` (behavior 1, AC-2): the 6.5.4 and 6.7.4 examples as whole reads give one page and one call.
  - `test_paged_read` (behavior 2, AC-2): each `*_paged_*` sequence gives its pages in order, equal to decoding each fixture alone; the calls' `start` values are the caller's `start` and then each `next`, and every call's `end` is the caller's.
  - `test_later_page_must_echo_cursor` (Review Focus 5).
  - `test_error_status_is_response_error` (behavior 7, AC-6): for each error body's status, as the first page: exactly `QuasarResponseError` with `status` and `code` from the body; `reason == "database_missing"` for the 503.
  - `test_error_status_on_later_page_returns_nothing` (spec 8): the same cases as the second response of a paged read; the same error, and no page is returned.
  - `test_not_ready_is_an_error_not_empty_data`: a `503 not_ready` never yields a page or an empty tuple.
  - `test_redirect_status_is_response_error`: `error(302, b"", None)` → `QuasarResponseError(302, None, None)`, one call.
  - `test_not_ready_reason`: 503 with and without `details.reason`.
  - `test_protocol_error_on_later_page_returns_nothing`: page 2 has a non-canonical price → `QuasarProtocolError`.
  - `test_injected_transport_errors_propagate` (behavior 8): a `QuasarTransportError` item propagates as the same object (`is`); a lambda transport returning `None` or a tuple raises `TypeError` (R8).
  - `test_injected_transport_programming_error_propagates` (spec 8): a `RuntimeError` item reaches the caller as the same object, not as a `QuasarClientError`.
  - `test_malformed_client_arguments_are_refused` (AC-8): the spec 8 list plus R7 cases (`"http://h /x"`, `"http://h\x00"`, `"ftp://h"`, `"http://"`, `"http://h:99999"`, `"http://h:abc"`, `"http://u:p@h"`, `"http://h/a;b"`, `"http://h/?"`, `"http://h/#"`, a `bytes` URL); `timeout_ms` `0`, `True`, `1.0`; each with the exact class of R4 (`ValueError` for both port cases), constructed with an injected `FakeTransport([])` whose `calls == []` afterwards.
  - `test_malformed_read_arguments_are_refused` (AC-8): the spec 8 list, each with the exact class of R4, and `FakeTransport([]).calls == []` after each.
  - `test_repeated_read_is_equal` (behavior 9): two reads over fake transports with the same bytes give equal tuples.

- [ ] **Step 2: Run the tests and see them fail (RED)**

  Run: `uv run pytest tests/infrastructure/test_client.py -q`. Expected: collection error, `client` does not exist.

- [ ] **Step 3: Implement `client.py` and `tests/infrastructure/quasar_fakes.py`**

  As under Interfaces. The client has exactly one `try`: around `value.encode("utf-8")` of an identifier, catching only `UnicodeEncodeError` and raising `ValueError(...) from None` (so the class is exactly `ValueError`). There is no other `try`: transport and decoder errors propagate as raised.

- [ ] **Step 4: Run the tests and see them pass (GREEN)**

  Run: `uv run pytest tests/infrastructure -q`. Expected: all pass.

- [ ] **Step 5: Run the gate and commit**

  Run: `make check`. Expected: clean, `passed`.

  ```bash
  git add src/sentaris_engine/infrastructure/quasar tests/infrastructure
  git commit -m "feat: SE-6 Quasar client reads and paging"
  ```

**Completion condition:** AC-1, AC-2, AC-6, AC-8 and behavior 1, 2, 7, 9 hold; `make check` passes.

---

### Task 4: Default urllib transport

**Implementer:** `sonnet`. Spec 5.6 fixes every handler and every caught exception; the tests run against real local servers.

**Files:** the Task 4 rows of the file structure table; `transport.py` gains `urllib_transport`; `__init__.py` exports it.

**Scope:** spec 5.6, 5.5 (default-transport guarantee, U4), behavior 8 (default part), AC-7; scope item 3 (`CLAUDE.md`).

**Interfaces:**
- Consumes `HttpResponse`, `QuasarTransportError`, `QuasarClient`.
- Produces `urllib_transport(url: str, timeout_ms: int) -> HttpResponse`, and in `tests/infrastructure/local_server.py` a pytest fixture `local_server` returning a factory `start(handler: Callable[[BaseHTTPRequestHandler], None]) -> Server`, where `Server` has `base_url: str` and `requests: list[tuple[str, dict[str, str]]]` (each received request line with its headers); servers run in daemon threads on `127.0.0.1:0` and are shut down at teardown.

  `urllib_transport` builds per call an opener with `urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())`, where `_NoRedirect(urllib.request.HTTPRedirectHandler)` returns `None` from `redirect_request`, so a `3xx` surfaces as `HTTPError`. It opens `Request(url, headers={"Accept": "application/json"}, method="GET")` with `timeout=timeout_ms / 1000` (the one `float`, spec 5.6). Exception handling, in this order and nowhere else: `except urllib.error.HTTPError as exc` → read `exc.read()` (an `OSError` or `http.client.HTTPException` there → `QuasarTransportError` from it), close it (`exc.close()` in `finally`) and return `HttpResponse(exc.code, exc.headers.get("Content-Type"), body)`; `except (OSError, http.client.HTTPException) as exc` → `raise QuasarTransportError(...) from exc`, around opening and reading the body only. Any response urllib returns normally (a `200`, and also a `201` or `204`) gives `HttpResponse(resp.status, resp.headers.get("Content-Type"), resp.read())`, read inside `with`, so the client's `status != 200` check judges it. No `ResourceWarning` remains.

- [ ] **Step 1: Write the failing tests in `tests/infrastructure/test_transport.py`**

  - `test_default_transport_reads_a_response`: a server answering the 6.5.4 example with `application/json; charset=utf-8` → `QuasarClient(server.base_url, 2000).read_open_interest(...)` gives the expected page; the server saw one `GET /v1/open-interest?...` request in origin form with `Accept: application/json`.
  - `test_non_200_is_a_status`: the 404 fixture with status 404 → `QuasarResponseError(404, "unknown_series", None)` through the client; a 500 with a non-JSON body → code `None`.
  - `test_redirect_is_not_followed`: origin answers `302` with `Location` pointing to a second server → `QuasarResponseError` with `status == 302`; the second server's `requests == []`.
  - `test_environment_proxy_is_ignored`: `monkeypatch.setenv` `HTTP_PROXY`, `http_proxy` (and `HTTPS_PROXY`, `https_proxy`) to a second server, `delenv` `NO_PROXY`, `no_proxy`; the read succeeds against the origin and the proxy's `requests == []`.
  - `test_requests_go_only_to_base_url_paths`: a three-page candle read sends three requests, each request line `GET /q/v1/candles?... HTTP/1.1` under a base URL with path prefix `/q`, each with header `Accept: application/json`.
  - `test_transport_failure_is_transport_error` (each case asserts exactly `QuasarTransportError` and the exact cause type, as CPython 3.12 produces it): a closed local port (bind, read the port, close) → `type(__cause__) is urllib.error.URLError` with `type(__cause__.reason) is ConnectionRefusedError`; a `200` that sends `Content-Length: 100`, 10 bytes, then closes → `type(__cause__) is http.client.IncompleteRead`; the same truncation on a `500` (read through the `HTTPError` path; Review Focus 6) → `type(__cause__) is http.client.IncompleteRead`; a server that sends nothing and waits on a `threading.Event` (set at teardown) with `timeout_ms=200` → `type(__cause__) is TimeoutError`. If a cause type differs on the machine, the implementer reports it instead of loosening the assertion.
  - `test_default_transport_programming_error_propagates`: `urllib_transport("not a url", 1000)` raises `ValueError` unchanged, not a `QuasarClientError` (spec 5.6: nothing else is caught).

- [ ] **Step 2: Run the tests and see them fail (RED)**

  Run: `uv run pytest tests/infrastructure/test_transport.py -q`. Expected: failures (stub or missing `urllib_transport`).

- [ ] **Step 3: Implement `urllib_transport` and `tests/infrastructure/local_server.py`**

  As under Interfaces.

- [ ] **Step 4: Run the tests and see them pass (GREEN)**

  Run: `uv run pytest tests/infrastructure -q`. Expected: all pass.

- [ ] **Step 5: Update `CLAUDE.md` "Current state"**

  Name SE-6 next to SE-1 to SE-5: SE-6 is the Quasar REST client in `sentaris_engine.infrastructure` (`quasar`), transport only. Change nothing else.

- [ ] **Step 6: Run the gate and commit**

  Run: `make check`. Expected: clean, `passed`.
  Run: `git diff main -- pyproject.toml uv.lock tests/architecture`. Expected: empty output (AC-10).

  ```bash
  git add src/sentaris_engine/infrastructure/quasar tests/infrastructure CLAUDE.md
  git commit -m "feat: SE-6 Quasar default urllib transport"
  ```

**Completion condition:** AC-7 and behavior 8 hold; `make check` passes; the AC-10 diff is empty.

---

## Acceptance criteria → tests

| AC | Tests |
|---|---|
| AC-1 | `test_request_urls`, `test_identifiers_are_encoded_and_echo_compared_decoded`, `test_base_url_forms`, `test_requests_go_only_to_base_url_paths` |
| AC-2 | `test_single_page_read`, `test_paged_read`, `test_later_page_must_echo_cursor` |
| AC-3 | `test_contract_examples_decode` |
| AC-4 | Task 1 body tests and every negative test of `test_decoding.py` |
| AC-5 | `test_decimal_text_is_exact`, `test_json_number_with_fraction_is_refused`, `test_no_float_is_built_for_ignored_fields`, `test_json_number_with_fraction_becomes_marker` |
| AC-6 | `test_error_classes`, `test_error_body_shapes`, `test_error_status_is_response_error`, `test_error_status_on_later_page_returns_nothing`, `test_protocol_error_on_later_page_returns_nothing`, `test_not_ready_reason`, `test_injected_transport_errors_propagate`, `test_injected_transport_programming_error_propagates`, `test_transport_failure_is_transport_error` |
| AC-7 | `test_redirect_is_not_followed`, `test_environment_proxy_is_ignored`, `test_non_200_is_a_status` |
| AC-8 | `test_malformed_client_arguments_are_refused`, `test_malformed_read_arguments_are_refused` |
| AC-9 | `test_unknown_fields_are_ignored` |
| AC-10 | `make check`; `git diff main -- pyproject.toml uv.lock tests/architecture` is empty (Task 4, Step 6) |
