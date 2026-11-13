# SE-6 — Quasar REST client: design

**Slice:** SE-6 (`docs/roadmap.md`, Phase A)  
**Status:** Revision 5, approved by the user (2026-11-13). Revision 5 corrects the wording of behavior 4 found by the plan review (HIGH-1): `str(Decimal("0.00000001"))` is `1E-8`, so exactness is stated through `format(d, "f")`; the behavior itself is unchanged. Revision 4 adds the user's two scoped clarifications (U4, U5): the transport error guarantee distinguishes the default transport from an injected one (5.5, 5.6, behavior 8), and the parse exceptions translated into `QuasarProtocolError` for a `200` body are listed exactly (5.4). Revision 3 fixes the scoped re-review of revision 2 (approved with changes: 1 MEDIUM, 5 LOW; none needed the user). Revision 1 was reviewed by Opus (`slice-reviewer`: approved with changes; 0 CRITICAL, 2 HIGH, 6 MEDIUM, 6 LOW). All findings are fixed in this revision; none needed the user, because each fix follows the domain document (6.1) or the Quasar contract (section 1, "Compatibility") rather than departing from them.  
**Domain references:** section 5; DR-06, DR-11, DR-15, DR-17, DR-18, DR-19, DR-21, DR-24; OD-3, OD-4, OD-6, OD-7, OD-24 (none decided here; see sections 10 and 11)  
**Quasar contract:** `../quasar-market-data/docs/contracts/api-v1.md`, sections 1, 2, 3, 5, 6.5, 6.7 (read 2026-11-13)

Decisions marked **[user Un]** were given by the user in the SE-6 conversation (section 12). Everything marked "my call" is an implementation choice the builder may keep or improve without changing behavior. Names of modules, classes and functions are indicative; the behavior is what is specified.

## 1. Goal

A transport-only client for three Quasar endpoints: `GET /v1/candles`, `GET /v1/open-interest` and `GET /v1/funding-rates`. Given Quasar's own series identifiers and an explicit window, it reads every page of the window, checks each response against the contract, parses decimals exactly, and returns the pages as separate, immutable values whose rows are the SE-3 row types. Any response outside the contract, any error answer and any transport problem is a typed client error; nothing is filled, defaulted or retried.

The client makes no statement about availability, completeness, freshness or consistency (roadmap SE-6 row; DR-06, DR-21, OD-24). It does not map an instrument key to a series (OD-4, SE-7b) and does not turn a client error into an evaluation failure (OD-3, SE-7b, SE-10).

## 2. Why this shape

| Choice | Derivation |
|---|---|
| Standard library only (`urllib.request`, `urllib.parse`, `json`) | **[user U1]**. No runtime dependency is added; `RUNTIME_ALLOWLIST` stays empty (SE-1 spec 6.3). Synchronous calls match sequential execution (section 6.7). |
| Pages are returned separately, never merged | **[user U2]**. Quasar pages are separate reads (contract section 3; domain section 5, "Pages are not a snapshot"). Merging them would hide the boundaries that OD-24 may need; returning them makes no claim that they are consistent with each other. |
| A page carries its echoed window, the series bounds, `next` and its rows; coverage, `as_of_ms` and `rule` are dropped | **[user U3]**. Those fields are computed at Quasar's clock and describe the present (contract 6.1.1; domain section 5; DR-21). Whether a later slice wants them is not SE-6's question. |
| Rows are SE-3's `Candle`, `OpenInterest`, `FundingRate` | Roadmap SE-3 row ("the row types of the three inputs"). The client builds them; their validation applies unchanged. |
| The `conflicted` flag is kept on every row | It is a field of the SE-3 rows and of the contract; what the engine does with it is OD-7. The client neither drops nor acts on it. |
| Errors are exceptions of the infrastructure layer, not results | The client is I/O, not an evaluation. How a client error becomes an evaluation failure, and with which code, is OD-3. |
| The client lives in `sentaris_engine.infrastructure` | SE-1 spec 5.2: `infrastructure` is the I/O adapter layer. It may import `sentaris_engine.domain` (for the rows and `check_instant`); the import-linter contracts keep it independent of `application` and `strategies`. |

## 3. Scope

1. A package `sentaris_engine.infrastructure.quasar` (my call; one or a few modules) with the client, the page types, the error types and the default HTTP transport.
2. Tests under `tests/infrastructure/`, with JSON fixtures under `tests/infrastructure/fixtures/` written from the contract (section 8).
3. `CLAUDE.md` "Current state" says that SE-6 exists.

Not in scope: any other Quasar endpoint (`/v1/coverage`, `/v1/open-interest/coverage`, `/v1/indicators`, `/v1/instruments`, `/health*`); see section 10.

## 4. Dependencies

SE-3 is merged on `main` (`40189df`); SE-4 and SE-5 are merged as well (`d5e229c`), and `make check` passes on `main` (1520 tests). SE-6 has no gate. No dependency is added and no architecture list is widened: `infrastructure` is not a pure package (SE-1 spec 6.1), so the stdlib allowlist does not apply to it, and the banned names (`BANNED_EVERYWHERE`) and the import-linter contracts apply unchanged.

## 5. Interfaces and contracts

### 5.1 Client construction

`QuasarClient(base_url, timeout_ms, transport=None)`:

- `base_url`: an exact `str`, an absolute `http` or `https` URL with a host and optionally a port, and nothing else of the URL syntax: no userinfo (`user:pass@`; the contract has no authentication, section 1 "Exposure", and the engine holds no credentials), no params (`;`), no query, no fragment. A path prefix is allowed and a trailing `/` is ignored. Anything else raises `ValueError` (my call). The client appends `/v1/candles`, `/v1/open-interest` or `/v1/funding-rates` and never builds any other URL.
- `timeout_ms`: a duration in the sense of domain 6.1, an exact `int` checked with SE-3's `check_duration`. It is passed to the transport for each request; only the default transport converts it to seconds, at the urllib call (review HIGH-1). Nothing is read from the environment: no base URL, no timeout, no proxy.
- `transport`: a callable `(url: str, timeout_ms: int) -> HttpResponse(status: int, content_type: str | None, body: bytes)`, raising `QuasarTransportError` on a network failure or timeout. `None` selects the default urllib transport (5.6). Tests inject a fake transport (my call). Any other exception an injected transport raises propagates unchanged (my call: the client classifies only what the contract and 5.5 define).

### 5.2 Read operations

Each operation reads the whole window, page by page, and returns `tuple[Page, ...]` with at least one page, in the order they were read.

| Operation | Quasar request | Window |
|---|---|---|
| `read_candles(venue, symbol, timeframe, start, end, limit=None)` | `GET /v1/candles` | `start <= open_time_ms < end` |
| `read_open_interest(venue, symbol, period, start, end, limit=None)` | `GET /v1/open-interest` | `start <= time_ms < end` |
| `read_funding_rates(venue, symbol, start, end_inclusive, limit=None)` | `GET /v1/funding-rates` | `start <= funding_time_ms <= end_inclusive` |

- `venue`, `symbol`, `timeframe`, `period`: exact non-empty `str`, sent as given. They are Quasar's identifiers; the client does not interpret them (no mapping of `"5m"` to milliseconds, OD-4).
- `start`, `end`, `end_inclusive`: exact `int`, checked with SE-3's `check_instant`.
- `end` is **required** (my call). A defaulted `end` is computed by Quasar from its newest stored row or, for funding, from its clock (contract 5.1, 6.5.2, 6.7.2); requiring it keeps every request window a function of the caller's arguments.
- The funding end is named `end_inclusive` (my call), because the contract's funding `end` is inclusive while the other two are exclusive (contract 6.7.2, decision FA1). The client passes Quasar's semantics through and converts nothing.
- `limit`: `None` (parameter omitted, server default 1000) or an exact `int` of at least 1, sent as ASCII digits. A `limit` below 1 cannot be written in the contract's integer syntax (`^[0-9]{1,16}$`, contract section 1) and raises `ValueError` locally; the upper bound (1000) and the funding minimum (2) are the server's to judge (my call).
- A malformed argument raises `TypeError` or `ValueError` before any request (my call). Ranges the server judges (alignment, window length, `limit` bounds, `end <= start`, valid time range of contract section 1) are not re-checked locally; the server's `400` becomes a `QuasarResponseError` (5.5).

**Query string.** Only documented parameters, each once, none empty (contract section 1, "Parameters"): `venue`, `symbol`, `timeframe` or `period`, `start`, `end`, and `limit` only when given. Each value is encoded as UTF-8 and every byte is percent-encoded with uppercase hex except ASCII letters, digits and `-._~/:` (that is, `urllib.parse.quote(value, safe="/:")`); this leaves `/` and `:` unencoded and encodes `%`, `+`, `&`, `#`, space and non-ASCII, as contract section 1 ("Encoding") requires. A `str` that cannot be encoded as UTF-8 (a lone surrogate) raises `ValueError` before any request. Integers are sent as ASCII decimal digits. The parameter order is fixed (my call), so a request URL is a function of the arguments.

**Paging** (contract sections 3 and 6.7.3). The first request uses the caller's `start` and `end`. While a page's `next` is not `null`, the next request uses `start = next` and the same `end` (the caller's, which the page echoes; 5.4). The loop terminates because every accepted `next` is strictly greater than the previous request's `start` and within the window (5.4).

### 5.3 Page types

Frozen, final, compared by their fields (my call: SE-3 conventions; `__init_subclass__` refuses subclassing).

- **`SeriesBounds(oldest, newest)`**: two instants with `oldest <= newest`.
- **`CandlePage(start, end, series, rows, next)`**: `start`, `end` the echoed window; `series` a `SeriesBounds` from `series.oldest_open_time_ms` and `series.newest_open_time_ms`; `rows` an exact `tuple` of `Candle`; `next` an instant or `None`.
- **`OpenInterestPage(start, end, series, rows, next)`**: as above, from `series.oldest_time_ms` and `series.newest_time_ms`, rows of `OpenInterest`.
- **`FundingRatePage(start, end_inclusive, series, rows, next)`**: `series` is a `SeriesBounds` or `None`, from `series.oldest_funding_time_ms` and `series.newest_funding_time_ms`, which the contract allows to be `null` together (contract 6.7.4, decision FA4); rows of `FundingRate`.

A page is what Quasar answered to one request. It is not a snapshot, carries no statement about coverage, and its `series` describes the series at the moment of that request only.

### 5.4 Response checks

Every `200` response is checked in full before a page is built; the first violation raises `QuasarProtocolError` (5.5). The client checks the fields it reads; fields it does not read are ignored, because the contract requires clients to ignore unknown fields and allows new ones within `/v1` (contract section 1, "Compatibility").

**Body.**

- `Content-Type`: the media type, compared case-insensitively (RFC 9110), is `application/json`. A `charset` parameter, if present, is `utf-8`, compared case-insensitively; other parameters are ignored (my call).
- The body is decoded strictly as UTF-8 (no BOM, no detection of UTF-16 or UTF-32), then parsed as JSON (RFC 8259); its top level is an object.
- **No `float` is ever built while decoding** (DR-11; the one `float` of the client is the socket timeout of 5.6). A JSON number with a fraction or exponent is decoded into an opaque marker that is neither a number nor a string (for example through a `parse_float` hook that keeps the raw text in a private type). Wherever the client reads a field, the marker fails the field's type check; in a field the client ignores it is ignored with the rest of that field (review HIGH-2).
- Refused anywhere in the body, as deliberate exceptions to "ignored", because they make the body not unambiguous JSON: `NaN`, `Infinity` and `-Infinity` (not JSON under RFC 8259), and an object with a repeated key (RFC 8259 leaves its meaning undefined; no occurrence wins) (my call).
- **Exceptions translated while parsing a `200` body.** Decoding and parsing are two calls, the strict UTF-8 decode and one `json.loads` with the client's own hooks (`parse_float`, `parse_int`, `parse_constant`, `object_pairs_hook`). Exactly these exceptions, raised by those two calls, become `QuasarProtocolError`, with the original chained as its cause:

  | Exception | Raised by | Case |
  |---|---|---|
  | `UnicodeDecodeError` | the strict UTF-8 decode | a body that is not UTF-8 |
  | `json.JSONDecodeError` | `json.loads` | malformed JSON, a BOM, an empty body, trailing data |
  | `RecursionError` | `json.loads` | nesting deeper than the parser can handle |
  | the client's private refusal error | the client's own hooks | `NaN`, `Infinity` and `-Infinity` (`parse_constant`); a repeated key in an object (`object_pairs_hook`); an integer longer than Python's integer-string digit limit (`parse_int`, which converts with `int(text)` and turns only that call's `ValueError` into the refusal error) |

  No other exception is caught there: no `except Exception`, no bare `except`, and no `ValueError` caught around `json.loads` as a whole, so a programming error in a hook or in the client propagates unchanged. The checks of 5.4 that run on the parsed tree raise `QuasarProtocolError` directly, without catching anything. The only other translation is the one stated below for rows: the SE-3 row constructor's `EvaluationTypeError`, caught around that constructor call alone. A non-`200` body is judged only by the predicate of 5.5.
- A missing `Content-Type` (the transport returns `None`) is refused.
- Unknown fields are ignored, at the top level, in `series` and in rows. Fields the page does not carry (`coverage`, `as_of_ms`, `rule`) are ignored without being checked (**[user U3]**).

**Echoed fields.**

- `venue` and `symbol` equal the request's; `timeframe` (candles) or `period` (open interest) equals the request's.
- `time_semantics` is `"period_end"` for open interest and `"settlement"` for funding (contract 6.5.4, 6.7.4). Any other value means the row's time is not what the SE-3 row type says it is (DR-24), so it is refused.
- `start` and `end` equal the request's `start` and `end`. The client always sends an explicit `end`, so the echo is exact (contract 5.1, 6.5.2, 6.7.2).

**Series.** `series` is an object holding the two fields of 5.3, each an instant (exact JSON integer accepted by `check_instant`), with `oldest <= newest`. For funding both may be `null`, together only.

**Rows.** `candles` (candles) or `rows` (open interest, funding) is an array of objects. Every documented field is present with its documented JSON type; a missing field is refused, never defaulted (DR-15).

| Endpoint | Field | JSON type | Becomes |
|---|---|---|---|
| candles | `open_time_ms` | integer | `Candle.open_time` |
| | `open`, `high`, `low`, `close`, `volume` | unsigned decimal string | `Decimal` |
| | `turnover` | unsigned decimal string or `null` | `Decimal` or `None` |
| | `conflicted` | boolean | `bool` |
| open interest | `time_ms` | integer | `OpenInterest.time` |
| | `open_interest`, `open_interest_value` | unsigned decimal string | `Decimal` |
| | `conflicted` | boolean | `bool` |
| funding | `funding_time_ms` | integer | `FundingRate.funding_time` |
| | `rate_type` | `"Regular"` or `"Special"` | `str` |
| | `funding_rate` | signed decimal string | `Decimal` |
| | `mark_price` | unsigned decimal string or `null` | `Decimal` or `None` |
| | `conflicted` | boolean | `bool` |

- An integer is a JSON integer (never `true`/`false`, never a string, never a fraction marker), accepted by `check_instant`.
- A field whose type is not "or `null`" in the table refuses `null`; `null` is never read as a default (DR-15).
- `rate_type` is exactly `"Regular"` or `"Special"`, case-sensitively.
- An **unsigned decimal string** is the canonical form of contract section 1: `0` or a digit string without a leading zero, optionally followed by `.` and digits that do not end in `0`; no sign, no exponent, no whitespace. It is matched with `re.fullmatch` against `(0|[1-9][0-9]*)(\.[0-9]*[1-9])?`, with the ASCII class `[0-9]`, never `\d`, and never with `re.match` and `$`, which would accept a trailing newline that `Decimal` then strips (review MEDIUM-1). A **signed decimal string** additionally allows one leading `-`, but not on a zero value (`"-0"` is refused; contract 6.7.1). A string outside the form is refused, not normalised.
- The text is converted with `Decimal(text)` and never passes through `float` (DR-11). The resulting `Decimal` keeps the text's exact digits and exponent.
- The SE-3 row constructor then applies its own checks; its `EvaluationTypeError` is turned into `QuasarProtocolError` (my call: a row the contract allows but SE-3 refuses cannot arise from canonical text, so this is defensive).

**Order and window.**

- Rows are strictly ascending: candles by `open_time_ms`, open interest by `time_ms`, funding by `(funding_time_ms, rate_type)` with `Regular` before `Special` (contract 5.2, 6.5.4, 6.7.3). A repeated key is refused.
- Every row lies in the request's window (5.2): candles and open interest `start <= time < end` (a row at `end` is refused), funding `start <= funding_time_ms <= end_inclusive` (a row at `end_inclusive` is accepted).
- A page holds at most `limit` rows, 1000 when `limit` is `None` (contract section 3, "at most `limit`"; 5.1, 6.5.2, 6.7.2).

**`next`.** Present on every page (contract section 3), `null` or an instant (a JSON integer; a string, boolean or fraction marker is refused).

- Candles and open interest: when rows were returned, `next` is `null` or `last returned time < next < end` (`next == end` is refused); when no row was returned, `next` is `null` (contract section 3: `null` "also when nothing was returned").
- Funding: when rows were returned, `next` is `null` or `last returned funding_time_ms < next <= end_inclusive` (`next == end_inclusive` is accepted); when no row was returned, `next` is `null` (contract 6.7.3).

What the client does **not** check, because the contract does not make it a property of a single response, because it needs knowledge the client does not have, or because it follows from the checks above only with extra assumptions:

- alignment of times to the timeframe or period (that needs the meaning of `"5m"`, OD-4);
- that a non-`null` `next` comes with a full page (candles and open interest `len(rows) == limit`, funding `len(rows) >= limit − 1`); the contract implies it, but the client does not depend on it (my call);
- that a row of one page agrees with a row of another page, or that two pages describe one moment (OD-24);
- anything about coverage, gaps, freshness or availability (DR-06, DR-21, OD-6, OD-7).

### 5.5 Errors

All client errors derive from one base, `QuasarClientError` (my call: an `Exception` subclass, not an `EvaluationTypeError`). The three kinds are distinct classes:

- **`QuasarTransportError`**: the request did not produce an HTTP response (connection refused, DNS, TLS, timeout, reset, a body that could not be read). The client itself never raises it; a transport does. The **default transport** guarantees that every network and I/O failure it documents (5.6) arrives as `QuasarTransportError`. An **injected transport** signals a transport failure by raising `QuasarTransportError`; any other exception it raises, a programming error included, propagates unchanged and is not translated by the client (5.1). The guarantee "a transport failure is a `QuasarTransportError`" therefore holds for the default transport, and for an injected one only as far as that transport keeps the 5.1 contract.
- **`QuasarResponseError(status, code, reason)`**: an HTTP status other than `200`. `status` is the integer status. `code` is read by this minimal predicate (my call, review MEDIUM-5): the body decodes as UTF-8 JSON under the rules of 5.4 (the `Content-Type` is not checked; a decode or parse failure is detected through exactly the exceptions listed in 5.4, which here give `code = None` instead of a `QuasarProtocolError`), its top level is an object, `error` is an object, and `error.code` is an exact non-empty `str`; then `code` is that string, else `None`. `message` and `details` are not required. A body that fails the predicate in any way gives `code = None` and is never a `QuasarProtocolError` (for example a server-generated error, contract section 2, "Out of this contract"). Any `code` string is carried as given, since new codes are additive. `reason` is `error.details.reason` only when `status == 503`, `code == "not_ready"`, `details` is an object and `reason` an exact `str`, else `None`. Nothing else of the body is carried. A `3xx` status is a `QuasarResponseError` too; the client never follows a redirect (5.6).
- **`QuasarProtocolError`**: a `200` response that breaks a check of 5.4.

No error is retried and no error is turned into an empty page, an empty tuple or `None` (contract section 2: "Clients must treat `503` as 'no data', never as 'empty data'"; this supports DR-14 and DR-15 downstream). A failure on any page fails the whole read: no partial tuple of pages is returned (my call). The client never sleeps and never reads `Retry-After` (my call: a retry policy is not decided anywhere, and retrying would make a read's duration and outcome depend on time).

Error messages may name the field and the rule broken. They are infrastructure diagnostics; what reaches a report is decided with OD-3.

### 5.6 Default transport

Built on `urllib.request`; it converts `timeout_ms` to seconds (`timeout_ms / 1000`) at the urllib call only. That `float` is the only one in the client: it exists only as the argument the socket layer requires, is never stored and never reaches a value the engine holds, and is not market data (DR-11) or an instant or duration of the engine (domain 6.1, where the timeout stays integer milliseconds). Its opener:

- uses no proxy (an empty `ProxyHandler`), so nothing is taken from the environment;
- does not follow redirects: a `3xx` is returned to the client as a status, which raises `QuasarResponseError`;
- sends `GET` only, with `Accept: application/json`, in origin form (urllib's default);
- returns the status, the `Content-Type` and the body of every response, including non-`200` ones (an `HTTPError` is read as a response, not raised further);
- turns exactly these documented network and I/O failures into `QuasarTransportError`, with the original chained as its cause: `OSError` and its subclasses (which include `urllib.error.URLError` other than `HTTPError`, `TimeoutError`, `ConnectionError`, `socket.gaierror` and `ssl.SSLError`), and `http.client.HTTPException` and its subclasses (for example `IncompleteRead`, `RemoteDisconnected`). They are caught only around opening the request and reading the response body. An `HTTPError` is handled first, as a response (previous point); an `OSError` while reading its body is a transport failure as well. Nothing else is caught: a `ValueError`, `TypeError` or any other exception from urllib or from the transport's own code propagates unchanged.

No caching, no compression negotiation, no authentication (contract section 1, "Exposure"; section 7).

## 6. Expected behavior

1. A read whose first page has `next: null` makes one request and returns one page.
2. A read across several pages makes one request per page, each continuing at the previous `next` with the caller's `end`, and returns the pages in order. The rows of different pages are not merged, deduplicated or reconciled.
3. A read of an existing series with nothing in the window returns one page with no rows (contract 5.2, 6.5.5, 6.7.6). This is Quasar's answer, not a statement that nothing exists (contract 5.3).
4. A decimal string is returned as exactly that `Decimal`: for `"82709"`, `"0.00000001"`, `"-0.00005123"` and a long coefficient such as `"12345678901234567890.123456789"`, the `Decimal` keeps the text's exact digits and exponent, so `format(d, "f")` gives the text back (`str(d)` may use scientific notation, for example `1E-8`).
5. `turnover: null` and `mark_price: null` become `None`; an absent `turnover` or `mark_price` is a protocol error.
6. `conflicted: true` is kept on the row; the client does nothing else with it.
7. A `400`, `404`, `405`, `500` or `503` answer, on any page, raises `QuasarResponseError` with its status and code; nothing is returned.
8. A network or I/O failure in the default transport raises `QuasarTransportError`. An injected transport's `QuasarTransportError` propagates as raised; any other exception from an injected transport propagates unchanged (5.1, 5.5).
9. Repeating a read against a fake transport that gives the same bytes gives equal pages (the client adds no time, id or randomness; DR-09).

## 7. Acceptance criteria

- **AC-1** Each operation sends exactly the documented parameters, encoded as in 5.2, to the right path under `base_url`, and only `GET`.
- **AC-2** Paging follows `next` with the caller's `end` and returns every page separately, in order; one page when `next` is `null`.
- **AC-3** The contract examples of sections 5.2, 6.5.4 and 6.7.4, used verbatim as fixtures, are read into the expected pages and rows, field by field. Each is the answer to the request it echoes, with an explicit `end` equal to its echoed `end` and, for 5.2, `limit=3`. The open interest and funding examples have `next: null` and are read as whole reads of one page. The candle example has a non-`null` `next`, so it is checked through the decoding of one page (the function that turns one response into one page; my call that it is testable on its own); paging is shown on the hand-written sequences of section 8 (review builder question 5).
- **AC-4** Every check of 5.4 refuses a response that breaks it, each with its own negative test (section 8).
- **AC-5** Decimals are exact (behavior 4); no field the client reads accepts a JSON number with a fraction or exponent; and no `float` is constructed while decoding any body, read fields and ignored fields alike.
- **AC-6** Errors are classified as in 5.5, carry the stated fields, and a failure on a later page returns nothing.
- **AC-7** The default transport sends no request through a proxy, follows no redirect, and reports a non-`200` response as a status; shown against a local HTTP server on `127.0.0.1` in the tests (my call).
- **AC-8** Malformed client or operation arguments are refused before any request.
- **AC-9** Unknown response fields are ignored at every level.
- **AC-10** `make check` passes; no dependency is added and no architecture list is changed.

## 8. Tests

**Fixtures.** JSON response bodies under `tests/infrastructure/fixtures/`, written by hand from the contract: the three examples of contract 5.2, 6.5.4 and 6.7.4 verbatim; a multi-page sequence for each endpoint (including a funding page boundary next to a `Regular`/`Special` pair, contract 6.7.3); an empty page; a funding page with `series` `null`; error bodies of contract section 2 for each status. Each fixture names the contract section it follows. Negative cases are derived from a valid fixture by changing one field in the test, so each test breaks exactly one rule.

**Negative tests** (names indicative). Each test is parametrised over the three endpoints where the check applies to more than one.

| Guarantee | Test |
|---|---|
| DR-11, no `float` | `test_json_number_with_fraction_is_refused` (a price as `82709.5` and as `8.27E4`, a time as `1.7926434E12`), `test_no_float_is_built_for_ignored_fields` (the single-page decode function is run on a body with a fractional number in an unknown field and in `coverage`; the test walks the decoded JSON tree at every depth and asserts that it holds no `float` instance and that those numbers became the marker type; removing the marker hook makes it fail), `test_nan_and_infinity_are_refused` (also inside an ignored field) |
| DR-11, exact text | `test_non_canonical_decimal_is_refused` (`"82709.0"`, `"082709"`, `"+1"`, `"1e3"`, `"1E3"`, `" 1"`, `"1 "`, `"1\n"`, `""`, `"."`, `"1."`, `".5"`, a non-ASCII digit string such as `"١٢"`, `"-0"` for funding, `"-1"` for a price) |
| DR-15, no defaults | `test_missing_row_field_is_refused` (each documented field in turn), `test_null_in_non_nullable_field_is_refused` (each non-nullable row field in turn), `test_missing_next_is_refused`, `test_missing_series_is_refused` |
| 5.5, an error is never data | `test_error_status_on_later_page_returns_nothing`, `test_not_ready_is_an_error_not_empty_data` |
| 5.6, only the configured base URL | `test_redirect_is_not_followed` (the redirect target, a second local server, receives no request), `test_environment_proxy_is_ignored` (`HTTP_PROXY` and `http_proxy` point to a second local server and `NO_PROXY`/`no_proxy` are cleared; the proxy receives nothing and the origin receives the request), `test_requests_go_only_to_base_url_paths` |
| Time semantics of the rows (supports DR-24) | `test_wrong_time_semantics_is_refused` (open interest, funding; missing and different value) |
| 5.4 body | `test_non_json_content_type_is_refused` (including an absent `Content-Type`), `test_non_utf8_charset_is_refused`, `test_invalid_utf8_body_is_refused`, `test_utf16_body_is_refused`, `test_top_level_not_object_is_refused`, `test_duplicate_json_key_is_refused` (also inside an ignored field), `test_oversized_integer_and_deep_nesting_are_protocol_errors` |
| 5.4 echoed fields and series | `test_missing_echoed_field_is_refused` (`venue`, `symbol`, `timeframe`/`period`, `start`, `end`, `time_semantics` in turn), `test_missing_rows_key_is_refused`, `test_echoed_identifier_mismatch_is_refused`, `test_echoed_window_mismatch_is_refused`, `test_series_not_object_is_refused`, `test_series_field_missing_null_or_wrong_type_is_refused` (candles and open interest: each bound missing, `null`, a string), `test_series_bounds_inverted_is_refused`, `test_funding_series_half_null_is_refused` |
| 5.4 rows | `test_rows_not_array_is_refused`, `test_row_not_object_is_refused`, `test_wrong_json_type_is_refused` (bool for an integer, integer for a decimal string, string for `conflicted`), `test_instant_out_of_range_is_refused` (negative, above 2^53 − 1), `test_unknown_rate_type_is_refused` (`"regular"`, `"Other"`), `test_rows_not_ascending_are_refused`, `test_duplicate_row_key_is_refused`, `test_row_outside_window_is_refused` (including a candle or open interest row at `end`), `test_more_rows_than_limit_are_refused` |
| 5.4 `next` | `test_next_wrong_type_is_refused` (string, boolean, fraction), `test_next_not_after_last_row_is_refused`, `test_next_outside_window_is_refused` (including candle or open interest `next == end`), `test_next_with_no_rows_is_refused` |
| 5.1, 5.2 arguments | `test_malformed_client_arguments_are_refused` (base URL without a host, with an invalid port, with userinfo, params, query, fragment, non-http scheme; `timeout_ms` not accepted by `check_duration`), `test_malformed_read_arguments_are_refused` (empty or non-`str` identifiers, a lone surrogate, non-instant times, non-`int` limit, `limit` 0); each asserts that the fake transport was never called |
| 5.5 classification | `test_error_body_shapes` (contract body: `code` set; non-JSON body, non-string `code`, missing `error`: `code` is `None`), `test_redirect_status_is_response_error`, `test_not_ready_reason` (with and without `reason`), `test_transport_failure_is_transport_error` (default transport: connection refused to a closed local port, a server that closes the connection mid-body, a read timeout), `test_injected_transport_programming_error_propagates` (an injected transport raising `RuntimeError` reaches the caller unchanged, not as a `QuasarClientError`) |
| 5.4 parse exceptions | `test_parse_failures_are_protocol_errors` (one case per row of the 5.4 exception table, each asserting the cause), `test_hook_programming_error_propagates` (a hook replaced in the test by one raising `RuntimeError` reaches the caller unchanged, so no broad handler surrounds the parse) |

**Positive boundary tests:** a funding row at `end_inclusive` and a funding `next == end_inclusive` are accepted; a candle or open interest row at `end − 1` is accepted.

**Positive tests** cover AC-1 to AC-3, AC-5, AC-6, AC-8, AC-9 and behavior 1 to 9.

DR-18 and DR-19 at the level of imports and dependencies stay enforced by the SE-1 architecture tests, which this slice does not change. DR-17 is not claimed as enforced by this slice: it forbids weakening validation, which no test can show; the tests above fail if a check is weakened.

**DR-07 does not apply here** (review LOW-1). The client has no `as_of` and filters nothing; the tests with data stamped after `as_of` belong to the snapshot builder slices that introduce each input (roadmap SE-7b, SE-8, SE-9).

## 9. Enforced guarantees and known limitations

- **Enforced, with the negative tests of section 8:** DR-11 at the client boundary (no `float` built, exact canonical text in every field read); DR-15 at the client boundary (no default for a missing or `null` field); an error answer is never returned as data (5.5, contract section 2); the default transport reaches only the configured base URL (no redirect, no proxy; 5.6).
- **Supported, not enforced by this slice:** DR-14 (the client produces no result; it gives later slices an error, never an empty answer); DR-24 (the client refuses a response whose stated time semantics differ from the SE-3 rows; relating inputs is the snapshot builder's).
- **Not a statement by the client, and not enforced here:** availability (DR-01 to DR-06), revision and conflict handling (DR-20, OD-7), completeness and freshness (DR-16, DR-21), consistency across pages (OD-24). SE-7b and later slices own these.
- **Limitation:** the client checks a single response; it cannot detect that a later page reflects a database changed since an earlier page (contract section 3). This is why pages are returned separately (**[user U2]**).
- **Limitation:** times are checked against `check_instant` (domain 6.1), not against Quasar's narrower valid range (contract section 1); a time outside Quasar's range would be Quasar's bug (my call).

## 10. Exclusions

- Mapping an instrument key to a series, and checking a key against Quasar data (OD-4, SE-7b).
- Any judgment of availability, staleness, coverage, gaps or conflicts (OD-6, OD-7, OD-8, OD-24; SE-7b to SE-10).
- Turning a client error into an evaluation failure, and its code (OD-3).
- The endpoints `/v1/coverage`, `/v1/open-interest/coverage`, `/v1/indicators` (not an approved input, OD-9), `/v1/instruments` (OD-4), `/health*`.
- Retries, back-off, rate limiting, caching, concurrency, async I/O, authentication.
- A configuration file or environment variables for the base URL or the timeout; that belongs to the composition root (SE-13).

## 11. Open questions

None for the user at revision 4. The domain document needs no change: the client adds no rule, and every open decision it touches (OD-3, OD-4, OD-6, OD-7, OD-24) stays open and is listed in section 10.

## 12. Decisions by the user (2026-11-13)

- **U1** HTTP library: the standard library (`urllib`), no runtime dependency.
- **U2** Paging: the client follows `next` to the end of the window and returns the pages separately, never merged into one sequence; it makes no claim that they are consistent (OD-24 stays open).
- **U3** A page carries its echoed window, the series bounds and `next` besides its rows; coverage blocks, `as_of_ms` and `rule` are dropped.
- **U4** The default transport translates its documented network and I/O failures into `QuasarTransportError`; an injected transport may let unexpected programming exceptions propagate unchanged (5.1), and the overall guarantee says so (5.5).
- **U5** The JSON parsing exceptions translated into `QuasarProtocolError` for a `200` body are defined exactly; no broad handler may hide a programming error. The behavior for malformed JSON, oversized integers, excessive nesting, duplicate keys and non-standard JSON constants is unchanged (5.4).
