"""The single-page decoders (SE-6 spec 5.4 "Echoed fields", "Series", "Rows", "Order and window", "`next`";
AC-3, AC-4, AC-5, AC-9; behavior 3 to 6). Negative cases are one edit of a valid fixture (spec 8)."""

import dataclasses
import itertools
import json
from decimal import Decimal
from typing import Final, NamedTuple, NoReturn

import pytest

from sentaris_engine.domain.errors import EvaluationTypeError
from sentaris_engine.domain.rows import Candle, FundingRate, OpenInterest
from sentaris_engine.infrastructure.quasar import (
    CandlePage,
    FundingRatePage,
    OpenInterestPage,
    QuasarProtocolError,
    SeriesBounds,
    decoding,
)
from tests.infrastructure.quasar_bodies import (
    BODIES,
    DELETE,
    FIXTURES,
    REQUESTS,
    Page,
    Raw,
    decode,
    decode_as,
    edited,
    load,
)


class Endpoint(NamedTuple):
    example: str  # the contract example
    tail: str  # a body with rows and `next: null`
    first: str  # a body with rows and a non-null `next`
    rows: str
    time: str
    price: str  # an unsigned decimal field
    oldest: str
    newest: str
    identifiers: tuple[str, ...]
    fields: tuple[str, ...]  # every documented row field (spec 5.4 table)
    nullable: tuple[str, ...]


ENDPOINTS: Final[dict[str, Endpoint]] = {
    "candles": Endpoint(
        "candles_example",
        "candles_paged_3",
        "candles_paged_1",
        "candles",
        "open_time_ms",
        "open",
        "oldest_open_time_ms",
        "newest_open_time_ms",
        ("venue", "symbol", "timeframe"),
        ("open_time_ms", "open", "high", "low", "close", "volume", "turnover", "conflicted"),
        ("turnover",),
    ),
    "open_interest": Endpoint(
        "open_interest_example",
        "open_interest_example",
        "open_interest_paged_1",
        "rows",
        "time_ms",
        "open_interest",
        "oldest_time_ms",
        "newest_time_ms",
        ("venue", "symbol", "period"),
        ("time_ms", "open_interest", "open_interest_value", "conflicted"),
        (),
    ),
    "funding": Endpoint(
        "funding_example",
        "funding_example",
        "funding_paged_1",
        "rows",
        "funding_time_ms",
        "mark_price",
        "oldest_funding_time_ms",
        "newest_funding_time_ms",
        ("venue", "symbol"),
        ("funding_time_ms", "rate_type", "funding_rate", "mark_price", "conflicted"),
        ("mark_price",),
    ),
}

ECHOED_WINDOW: Final = ("start", "end")
TIME_SEMANTICS: Final = {"open_interest": "period_end", "funding": "settlement"}


class Edit(NamedTuple):
    name: str
    path: tuple[str | int, ...]
    value: object


def _tree(name: str) -> dict[str, object]:
    tree = json.loads(load(name))
    assert type(tree) is dict
    return tree


def _rows(name: str) -> list[dict[str, object]]:
    rows = _tree(name)[ENDPOINTS[REQUESTS[name].endpoint].rows]
    assert type(rows) is list
    return rows


def _last_time(name: str) -> int:
    time = _rows(name)[-1][ENDPOINTS[REQUESTS[name].endpoint].time]
    assert type(time) is int
    return time


def _params(cases: dict[str, Edit]) -> list[object]:
    return [pytest.param(case, id=key) for key, case in cases.items()]


def _refused(case: Edit) -> QuasarProtocolError:
    with pytest.raises(QuasarProtocolError) as info:
        decode(case.name, edited(case.name, case.path, case.value))
    assert type(info.value) is QuasarProtocolError
    return info.value


def _accepted(case: Edit) -> Page:
    return decode(case.name, edited(case.name, case.path, case.value))


def _decimal_fields(page: Page) -> list[tuple[str, Decimal]]:
    """`(field, value)` of every `Decimal` of the page's rows, in row order."""
    found: list[tuple[str, Decimal]] = []
    for row in page.rows:
        for field in dataclasses.fields(row):
            value = getattr(row, field.name)
            if type(value) is Decimal:
                found.append((field.name, value))
    return found


# --- index and fixtures ----------------------------------------------------------------------------------------------


def test_body_index_is_complete() -> None:
    assert {path.name for path in FIXTURES.iterdir()} == {f"{name}.json" for name in BODIES}
    ok_bodies = {name for name in BODIES if not name.startswith("error_")}
    assert set(REQUESTS) == ok_bodies


@pytest.mark.parametrize("name", sorted(REQUESTS))
def test_every_ok_body_decodes(name: str) -> None:
    page = decode(name)
    assert page == decode(name)  # behavior 9: same bytes, equal page


@pytest.mark.parametrize(
    "names",
    [
        ("candles_paged_1", "candles_paged_2", "candles_paged_3"),
        ("open_interest_paged_1", "open_interest_paged_2"),
        ("funding_paged_1", "funding_paged_2"),
    ],
)
def test_paged_sequences_continue_at_next(names: tuple[str, ...]) -> None:
    pages = [decode(name) for name in names]
    for page, following in itertools.pairwise(pages):
        assert page.next == following.start
    assert pages[-1].next is None
    for name, page in zip(names, pages, strict=True):
        limit = REQUESTS[name].limit
        assert limit is not None and len(page.rows) <= limit


def test_paged_fixture_shapes() -> None:
    # A gap between candle pages 1 and 2, so `next` is not `last + 300000`.
    first = decode("candles_paged_1")
    assert first.next is not None and first.next != _last_time("candles_paged_1") + 300000
    # Contract 6.7.3: with limit 3 the pair at t3 is not split.
    funding_1, funding_2 = decode("funding_paged_1"), decode("funding_paged_2")
    assert type(funding_1) is FundingRatePage and type(funding_2) is FundingRatePage
    assert [row.rate_type for row in funding_1.rows] == ["Regular", "Regular"]
    assert funding_1.next == funding_2.start
    assert [(row.funding_time, row.rate_type) for row in funding_2.rows] == [
        (funding_2.start, "Regular"),
        (funding_2.start, "Special"),
    ]


# --- contract examples (AC-3, behavior 4, 6) -------------------------------------------------------------------------


def test_contract_examples_decode() -> None:
    d = Decimal
    candles = decode("candles_example")
    assert candles == CandlePage(
        start=1792643400000,
        end=1792673400000,
        series=SeriesBounds(1792643400000, 1792673100000),
        rows=(
            Candle(
                1792643400000,
                d("82855.4"),
                d("82866.1"),
                d("82768.1"),
                d("82768.2"),
                d("369.221"),
                d("30587379.8759"),
                False,
            ),
            Candle(
                1792643700000,
                d("82768.2"),
                d("82768.2"),
                d("82664.7"),
                d("82709"),
                d("580.95"),
                d("48054366.2802"),
                False,
            ),
            Candle(
                1792644000000,
                d("82709.1"),
                d("82765.3"),
                d("82686.2"),
                d("82744.5"),
                d("380.864"),
                d("31506256.9708"),
                False,
            ),
        ),
        next=1792644300000,
    )
    assert type(candles) is CandlePage
    assert candles.next == 1792644300000
    assert candles.rows[1].close == Decimal(82709)
    assert format(candles.rows[1].close, "f") == "82709"
    assert candles.series == SeriesBounds(1792643400000, 1792673100000)

    open_interest = decode("open_interest_example")
    assert open_interest == OpenInterestPage(
        start=1792672500000,
        end=1792674600000,
        series=SeriesBounds(1792643700000, 1792673400000),
        rows=(
            OpenInterest(1792672500000, d("95677.779"), d("7446123150.675"), False),
            OpenInterest(1792672800000, d("95690.12"), d("7447031002.4"), True),
            OpenInterest(1792673400000, d("95702.5"), d("7447990111.25"), False),
        ),
        next=None,
    )
    assert type(open_interest) is OpenInterestPage
    assert open_interest.rows[1].conflicted is True

    funding = decode("funding_example")
    assert funding == FundingRatePage(
        start=1792656000000,
        end_inclusive=1792720000000,
        series=SeriesBounds(1792627200000, 1792713600650),
        rows=(
            FundingRate(1792656000000, "Regular", d("0.0001"), d("82709.1"), False),
            FundingRate(1792684800000, "Regular", d("-0.00005123"), d("82744.5"), False),
            FundingRate(1792713600000, "Regular", d("0.00011"), d("82790"), True),
            FundingRate(1792713600650, "Special", d("0.0003"), d("82801"), False),
        ),
        next=None,
    )
    assert type(funding) is FundingRatePage
    assert (funding.rows[3].rate_type, funding.rows[3].funding_time) == ("Special", 1792713600650)
    assert funding.rows[1].funding_rate == Decimal("-0.00005123")

    # Decimal equality is numeric; the text itself is compared through `format(value, "f")` (behavior 4).
    for name, page in (
        ("candles_example", candles),
        ("open_interest_example", open_interest),
        ("funding_example", funding),
    ):
        texts = [(field, row[field]) for row in _rows(name) for field in row if type(row[field]) is str]
        texts = [(field, text) for field, text in texts if field != "rate_type"]
        assert [(field, format(value, "f")) for field, value in _decimal_fields(page)] == texts


DECIMAL_TEXT_CASES: Final = {
    "tiny-price": (Edit("candles_example", ("candles", 0, "open"), "0.00000001"), "open", -8),
    "long-price": (Edit("candles_example", ("candles", 0, "high"), "12345678901234567890.123456789"), "high", -9),
    "negative-funding-rate": (Edit("funding_example", ("rows", 0, "funding_rate"), "-0.00005123"), "funding_rate", -8),
}


@pytest.mark.parametrize("case", DECIMAL_TEXT_CASES.values(), ids=DECIMAL_TEXT_CASES.keys())
def test_decimal_text_is_exact(case: tuple[Edit, str, int]) -> None:
    edit, field, exponent = case
    value = getattr(_accepted(edit).rows[0], field)
    assert type(value) is Decimal
    assert format(value, "f") == edit.value
    assert value.as_tuple().exponent == exponent
    if edit.value == "0.00000001":
        assert str(value) == "1E-8"  # `str` is not the check (spec behavior 4)


NULLABLE_CASES: Final = {
    f"{kind}-{field}": (e.example, (e.rows, 0, field)) for kind, e in ENDPOINTS.items() for field in e.nullable
}


@pytest.mark.parametrize("case", NULLABLE_CASES.values(), ids=NULLABLE_CASES.keys())
def test_nullable_fields(case: tuple[str, tuple[str | int, ...]]) -> None:
    name, path = case
    field = path[-1]
    assert type(field) is str
    page = _accepted(Edit(name, path, None))
    assert getattr(page.rows[0], field) is None
    _refused(Edit(name, path, DELETE))  # DR-15


# --- ignored fields (AC-9, AC-5) -------------------------------------------------------------------------------------


def _ignored_edits(name: str, endpoint: Endpoint) -> dict[str, Edit]:
    cases = {
        "top-level": Edit(name, ("unknown",), 1),
        "series": Edit(name, ("series", "unknown"), "x"),
        "row": Edit(name, (endpoint.rows, 0, "unknown"), True),
        "coverage": Edit(name, ("coverage", "unknown"), 1),
        "fraction-in-coverage": Edit(name, ("coverage", "unknown"), Raw("0.5")),
        "fraction-at-top-level": Edit(name, ("unknown",), Raw("-1.25E-3")),
        "exponent-in-row": Edit(name, (endpoint.rows, 0, "unknown"), Raw("1e3")),
    }
    for key in ("coverage", "as_of_ms", "rule"):
        cases[f"{key}-garbage"] = Edit(name, (key,), Raw('"garbage"'))
    return cases


IGNORED_CASES: Final = {
    f"{kind}-{key}": case
    for kind, endpoint in ENDPOINTS.items()
    for key, case in _ignored_edits(endpoint.example, endpoint).items()
}


@pytest.mark.parametrize("case", _params(IGNORED_CASES))
def test_unknown_fields_are_ignored(case: Edit) -> None:
    assert _accepted(case) == decode(case.name)


EMPTY_CASES: Final = {
    "candles": Edit("candles_empty", ("candles",), []),
    "open_interest": Edit("open_interest_paged_2", ("rows",), []),
    "funding": Edit("funding_paged_2", ("rows",), []),
}


@pytest.mark.parametrize("case", _params(EMPTY_CASES))
def test_empty_page(case: Edit) -> None:
    page = _accepted(case)
    assert page.rows == ()
    assert page.next is None
    assert page.series is not None


def test_funding_series_null() -> None:
    page = decode("funding_series_null")
    assert type(page) is FundingRatePage
    assert (page.series, page.rows, page.next) == (None, (), None)


# --- JSON values the decoder reads (DR-11) ---------------------------------------------------------------------------

FRACTION_CASES: Final = {
    f"{kind}-{key}": case
    for kind, e in ENDPOINTS.items()
    for key, case in {
        "price-fraction": Edit(e.example, (e.rows, 0, e.price), Raw("82709.5")),
        "price-exponent": Edit(e.example, (e.rows, 0, e.price), Raw("8.27E4")),
        "time-exponent": Edit(e.example, (e.rows, 0, e.time), Raw("1.7926434E12")),
        "next": Edit(e.example, ("next",), Raw("1.5")),
        "series-bound": Edit(e.example, ("series", e.oldest), Raw("1.5")),
    }.items()
}


@pytest.mark.parametrize("case", _params(FRACTION_CASES))
def test_json_number_with_fraction_is_refused(case: Edit) -> None:
    assert _refused(case).__cause__ is None


NAN_CASES: Final = {
    f"{kind}-{key}": case
    for kind, e in ENDPOINTS.items()
    for key, case in {
        f"{where}-{constant}": Edit(e.example, path, Raw(constant))
        for where, path in {"price": (e.rows, 0, e.price), "in-coverage": ("coverage", "unknown")}.items()
        for constant in ("NaN", "Infinity", "-Infinity")
    }.items()
}


@pytest.mark.parametrize("case", _params(NAN_CASES))
def test_nan_and_infinity_are_refused(case: Edit) -> None:
    _refused(case)


@pytest.mark.parametrize("kind", ENDPOINTS)
def test_duplicate_json_key_is_refused(kind: str) -> None:
    name = ENDPOINTS[kind].example
    original = b'"venue": "binance-usdm",'
    body = load(name)
    assert body.count(original) == 1
    with pytest.raises(QuasarProtocolError) as info:
        decode(name, body.replace(original, original + b' "venue": "binance-usdm",'))
    assert type(info.value) is QuasarProtocolError
    _refused(Edit(name, ("coverage", "unknown"), Raw('{"a":1,"a":2}')))


NON_CANONICAL: Final = (
    "82709.0",
    "082709",
    "+1",
    "1e3",
    "1E3",
    " 1",
    "1 ",
    "1\n",
    "",
    ".",
    "1.",
    ".5",
    "١٢",
    "1١",  # an ASCII digit first: `\d` instead of `[0-9]` would accept it (spec 5.4)
    "0.١5",
    "00",
    "0.",
    "-0.5",
)

NON_CANONICAL_CASES: Final = {
    **{
        f"{kind}-{e.price}-{text!r}": Edit(e.example, (e.rows, 0, e.price), text)
        for kind, e in ENDPOINTS.items()
        for text in (*NON_CANONICAL, "-1")
    },
    **{
        f"funding_rate-{text!r}": Edit("funding_example", ("rows", 0, "funding_rate"), text)
        for text in (*NON_CANONICAL[:-1], "-0", "-", "--1", "-01", "-+1", "- 1")
    },
}


@pytest.mark.parametrize("case", _params(NON_CANONICAL_CASES))
def test_non_canonical_decimal_is_refused(case: Edit) -> None:
    assert _refused(case).__cause__ is None


def test_signed_decimal_is_accepted_only_for_funding_rate() -> None:
    page = _accepted(Edit("funding_example", ("rows", 0, "funding_rate"), "-0.5"))
    assert type(page) is FundingRatePage and format(page.rows[0].funding_rate, "f") == "-0.5"
    _refused(Edit("funding_example", ("rows", 0, "mark_price"), "-0.5"))


MISSING_FIELD_CASES: Final = {
    f"{kind}-{field}": Edit(e.example, (e.rows, 0, field), DELETE)
    for kind, e in ENDPOINTS.items()
    for field in e.fields
}


@pytest.mark.parametrize("case", _params(MISSING_FIELD_CASES))
def test_missing_row_field_is_refused(case: Edit) -> None:
    assert _refused(case).__cause__ is None


NULL_FIELD_CASES: Final = {
    f"{kind}-{field}": Edit(e.example, (e.rows, 0, field), None)
    for kind, e in ENDPOINTS.items()
    for field in e.fields
    if field not in e.nullable
}


@pytest.mark.parametrize("case", _params(NULL_FIELD_CASES))
def test_null_in_non_nullable_field_is_refused(case: Edit) -> None:
    assert _refused(case).__cause__ is None


WRONG_TYPE_CASES: Final = {
    **{
        f"{kind}-{key}": case
        for kind, e in ENDPOINTS.items()
        for key, case in {
            "time-bool": Edit(e.example, (e.rows, 0, e.time), True),
            "time-string": Edit(e.example, (e.rows, 0, e.time), str(_rows(e.example)[0][e.time])),
            "price-integer": Edit(e.example, (e.rows, 0, e.price), 82709),
            "conflicted-string": Edit(e.example, (e.rows, 0, "conflicted"), "false"),
            "conflicted-0": Edit(e.example, (e.rows, 0, "conflicted"), 0),
            "conflicted-1": Edit(e.example, (e.rows, 0, "conflicted"), 1),
        }.items()
    },
    "funding-rate_type-integer": Edit("funding_example", ("rows", 0, "rate_type"), 1),
    "funding-funding_rate-integer": Edit("funding_example", ("rows", 0, "funding_rate"), 0),
}


@pytest.mark.parametrize("case", _params(WRONG_TYPE_CASES))
def test_wrong_json_type_is_refused(case: Edit) -> None:
    # The decoder refuses the JSON type itself, not the SE-3 row constructor.
    assert _refused(case).__cause__ is None


@pytest.mark.parametrize("rate_type", ["regular", "Other", "", "REGULAR", "Regular "])
def test_unknown_rate_type_is_refused(rate_type: str) -> None:
    assert _refused(Edit("funding_example", ("rows", 0, "rate_type"), rate_type)).__cause__ is None


OUT_OF_RANGE_CASES: Final = {
    f"{kind}-{key}-{value}": Edit(e.example, path, value)
    for kind, e in ENDPOINTS.items()
    for key, path in {"row": (e.rows, 0, e.time), "oldest": ("series", e.oldest), "next": ("next",)}.items()
    for value in (-1, 2**53)
} | {f"{kind}-newest-{2**53}": Edit(e.example, ("series", e.newest), 2**53) for kind, e in ENDPOINTS.items()}


@pytest.mark.parametrize("case", _params(OUT_OF_RANGE_CASES))
def test_instant_out_of_range_is_refused(case: Edit) -> None:
    assert _refused(case).__cause__ is None


# --- echoed fields ---------------------------------------------------------------------------------------------------

MISSING_ECHO_CASES: Final = {
    f"{kind}-{field}": Edit(e.example, (field,), DELETE)
    for kind, e in ENDPOINTS.items()
    for field in (*e.identifiers, *ECHOED_WINDOW, *(("time_semantics",) if kind in TIME_SEMANTICS else ()))
}


@pytest.mark.parametrize("case", _params(MISSING_ECHO_CASES))
def test_missing_echoed_field_is_refused(case: Edit) -> None:
    _refused(case)


IDENTIFIER_MISMATCH_CASES: Final = {
    f"{kind}-{field}-{value!r}": Edit(e.example, (field,), value)
    for kind, e in ENDPOINTS.items()
    for field in e.identifiers
    for value in ("other", "", 1, None, ["binance-usdm"])
} | {f"{kind}-symbol-case": Edit(e.example, ("symbol",), "btc/usdt:usdt") for kind, e in ENDPOINTS.items()}


@pytest.mark.parametrize("case", _params(IDENTIFIER_MISMATCH_CASES))
def test_echoed_identifier_mismatch_is_refused(case: Edit) -> None:
    _refused(case)


def _echo_value(name: str, field: str) -> int:
    value = _tree(name)[field]
    assert type(value) is int
    return value


WINDOW_MISMATCH_CASES: Final = {
    f"{kind}-{field}{delta:+}": Edit(e.example, (field,), _echo_value(e.example, field) + delta)
    for kind, e in ENDPOINTS.items()
    for field in ECHOED_WINDOW
    for delta in (-1, 1)
} | {
    f"{kind}-{field}-string": Edit(e.example, (field,), str(_echo_value(e.example, field)))
    for kind, e in ENDPOINTS.items()
    for field in ECHOED_WINDOW
}


@pytest.mark.parametrize("case", _params(WINDOW_MISMATCH_CASES))
def test_echoed_window_mismatch_is_refused(case: Edit) -> None:
    _refused(case)


TIME_SEMANTICS_CASES: Final = {
    f"{kind}-{value!r}": Edit(ENDPOINTS[kind].example, ("time_semantics",), value)
    for kind, expected in TIME_SEMANTICS.items()
    for value in (DELETE, "period_start", None, *(other for other in TIME_SEMANTICS.values() if other != expected))
}


@pytest.mark.parametrize("case", _params(TIME_SEMANTICS_CASES))
def test_wrong_time_semantics_is_refused(case: Edit) -> None:
    _refused(case)


@pytest.mark.parametrize("kind", ENDPOINTS)
def test_missing_rows_key_is_refused(kind: str) -> None:
    e = ENDPOINTS[kind]
    _refused(Edit(e.example, (e.rows,), DELETE))


@pytest.mark.parametrize("kind", ENDPOINTS)
def test_missing_next_is_refused(kind: str) -> None:
    _refused(Edit(ENDPOINTS[kind].example, ("next",), DELETE))  # DR-15


@pytest.mark.parametrize("kind", ENDPOINTS)
def test_missing_series_is_refused(kind: str) -> None:
    _refused(Edit(ENDPOINTS[kind].example, ("series",), DELETE))  # DR-15


_NOT_AN_OBJECT: Final[tuple[object, ...]] = (None, [], "x", 1, True)
_NOT_AN_ARRAY: Final[tuple[object, ...]] = ({}, "x", None)
_NOT_A_ROW: Final[tuple[object, ...]] = ([], "x", None, 1)


# --- series ----------------------------------------------------------------------------------------------------------

SERIES_NOT_OBJECT_CASES: Final = {
    f"{kind}-{value!r}": Edit(e.example, ("series",), value)
    for kind, e in ENDPOINTS.items()
    for value in _NOT_AN_OBJECT
}


@pytest.mark.parametrize("case", _params(SERIES_NOT_OBJECT_CASES))
def test_series_not_object_is_refused(case: Edit) -> None:
    _refused(case)


SERIES_FIELD_CASES: Final = {
    f"{kind}-{bound}-{value!r}": Edit(e.example, ("series", bound), value)
    for kind, e in ENDPOINTS.items()
    for bound in (e.oldest, e.newest)
    for value in (DELETE, "1792643400000", True, *((None,) if kind != "funding" else ()))
}


@pytest.mark.parametrize("case", _params(SERIES_FIELD_CASES))
def test_series_field_missing_null_or_wrong_type_is_refused(case: Edit) -> None:
    _refused(case)


def _series_bound(name: str, bound: str) -> int:
    series = _tree(name)["series"]
    assert type(series) is dict
    value = series[bound]
    assert type(value) is int
    return value


INVERTED_CASES: Final = {
    kind: (e.example, ("series", e.oldest), _series_bound(e.example, e.newest)) for kind, e in ENDPOINTS.items()
}


@pytest.mark.parametrize("case", INVERTED_CASES.values(), ids=INVERTED_CASES.keys())
def test_series_bounds_inverted_is_refused(case: tuple[str, tuple[str, ...], int]) -> None:
    name, path, newest = case
    _refused(Edit(name, path, newest + 1))
    equal = _accepted(Edit(name, path, newest))
    assert equal.series is not None and equal.series.oldest == equal.series.newest


HALF_NULL_CASES: Final = {
    "oldest-null": Edit("funding_example", ("series", "oldest_funding_time_ms"), None),
    "newest-null": Edit("funding_example", ("series", "newest_funding_time_ms"), None),
    "oldest-set": Edit("funding_series_null", ("series", "oldest_funding_time_ms"), 1792627200000),
    "newest-set": Edit("funding_series_null", ("series", "newest_funding_time_ms"), 1792627200000),
}


@pytest.mark.parametrize("case", _params(HALF_NULL_CASES))
def test_funding_series_half_null_is_refused(case: Edit) -> None:
    _refused(case)


# --- rows ------------------------------------------------------------------------------------------------------------

ROWS_NOT_ARRAY_CASES: Final = {
    f"{kind}-{value!r}": Edit(e.example, (e.rows,), value) for kind, e in ENDPOINTS.items() for value in _NOT_AN_ARRAY
}


@pytest.mark.parametrize("case", _params(ROWS_NOT_ARRAY_CASES))
def test_rows_not_array_is_refused(case: Edit) -> None:
    _refused(case)


ROW_NOT_OBJECT_CASES: Final = {
    f"{kind}-{value!r}": Edit(e.example, (e.rows, 0), value) for kind, e in ENDPOINTS.items() for value in _NOT_A_ROW
}


@pytest.mark.parametrize("case", _params(ROW_NOT_OBJECT_CASES))
def test_row_not_object_is_refused(case: Edit) -> None:
    _refused(case)


NOT_ASCENDING_CASES: Final = {
    kind: Edit(e.example, (e.rows,), _rows(e.example)[::-1]) for kind, e in ENDPOINTS.items()
} | {
    # Contract 6.7.3: `Regular` before `Special` at one `funding_time_ms`.
    "funding-special-before-regular": Edit("funding_paged_2", ("rows",), _rows("funding_paged_2")[::-1]),
}


@pytest.mark.parametrize("case", _params(NOT_ASCENDING_CASES))
def test_rows_not_ascending_are_refused(case: Edit) -> None:
    _refused(case)


DUPLICATE_ROW_CASES: Final = {
    kind: Edit(e.example, (e.rows, 1), _rows(e.example)[0]) for kind, e in ENDPOINTS.items()
} | {
    "funding-two-regular-at-one-time": Edit("funding_paged_2", ("rows", 1, "rate_type"), "Regular"),
}


@pytest.mark.parametrize("case", _params(DUPLICATE_ROW_CASES))
def test_duplicate_row_key_is_refused(case: Edit) -> None:
    _refused(case)


def _window_edit(kind: str, row: int, offset_from: str, delta: int) -> Edit:
    e = ENDPOINTS[kind]
    request = REQUESTS[e.tail]
    anchor = request.start if offset_from == "start" else request.end
    return Edit(e.tail, (e.rows, row, e.time), anchor + delta)


OUTSIDE_WINDOW_CASES: Final = {
    **{f"{kind}-start-1": _window_edit(kind, 0, "start", -1) for kind in ENDPOINTS},
    "candles-at-end": _window_edit("candles", -1, "end", 0),
    "open_interest-at-end": _window_edit("open_interest", -1, "end", 0),
    "funding-end_inclusive+1": _window_edit("funding", -1, "end", 1),
}

INSIDE_WINDOW_CASES: Final = {
    "candles-end-1": _window_edit("candles", -1, "end", -1),
    "open_interest-end-1": _window_edit("open_interest", -1, "end", -1),
    "funding-at-end_inclusive": _window_edit("funding", -1, "end", 0),
}


@pytest.mark.parametrize("case", _params(OUTSIDE_WINDOW_CASES))
def test_row_outside_window_is_refused(case: Edit) -> None:
    _refused(case)


@pytest.mark.parametrize("case", _params(INSIDE_WINDOW_CASES))
def test_row_at_window_edge_is_accepted(case: Edit) -> None:
    page = _accepted(case)
    assert page.rows[-1] != decode(case.name).rows[-1]


def _decode_with_limit(name: str, body: bytes, limit: int | None) -> Page:
    return decode_as(dataclasses.replace(REQUESTS[name], limit=limit), body)


def _generated_rows(kind: str, count: int) -> bytes:
    """The contract example with `count` rows one millisecond apart from `start` (within every example window)."""
    e = ENDPOINTS[kind]
    template = _rows(e.example)[0]
    start = REQUESTS[e.example].start
    rows = [template | {e.time: start + index} for index in range(count)]
    return edited(e.example, (e.rows,), rows)


@pytest.mark.parametrize("kind", ENDPOINTS)
def test_more_rows_than_limit_are_refused(kind: str) -> None:
    name = ENDPOINTS[kind].example
    count = len(_rows(name))
    _decode_with_limit(name, load(name), count)
    with pytest.raises(QuasarProtocolError) as info:
        _decode_with_limit(name, load(name), count - 1)
    assert type(info.value) is QuasarProtocolError

    # `limit=None` is the server default of 1000 (contract 5.1, 6.5.2, 6.7.2).
    assert len(_decode_with_limit(name, _generated_rows(kind, 1000), None).rows) == 1000
    with pytest.raises(QuasarProtocolError) as info:
        _decode_with_limit(name, _generated_rows(kind, 1001), None)
    assert type(info.value) is QuasarProtocolError


@pytest.mark.parametrize("kind", ENDPOINTS)
def test_full_last_page_with_null_next_is_accepted(kind: str) -> None:
    name = ENDPOINTS[kind].example
    page = _decode_with_limit(name, edited(name, ("next",), None), len(_rows(name)))
    assert page.next is None
    assert len(page.rows) == len(_rows(name))


# --- next ------------------------------------------------------------------------------------------------------------

NEXT_WRONG_TYPE_CASES: Final = {
    f"{kind}-{key}": Edit(e.first, ("next",), value)
    for kind, e in ENDPOINTS.items()
    for key, value in {"string": str(_tree(e.first)["next"]), "bool": True, "fraction": Raw("1.5")}.items()
}


@pytest.mark.parametrize("case", _params(NEXT_WRONG_TYPE_CASES))
def test_next_wrong_type_is_refused(case: Edit) -> None:
    _refused(case)


NEXT_NOT_AFTER_LAST_CASES: Final = {
    f"{kind}-{key}": Edit(e.first, ("next",), _last_time(e.first) + delta)
    for kind, e in ENDPOINTS.items()
    for key, delta in {"equal-to-last": 0, "before-last": -1}.items()
}


@pytest.mark.parametrize("case", _params(NEXT_NOT_AFTER_LAST_CASES))
def test_next_not_after_last_row_is_refused(case: Edit) -> None:
    _refused(case)


def _next_edit(kind: str, delta: int) -> Edit:
    e = ENDPOINTS[kind]
    return Edit(e.first, ("next",), REQUESTS[e.first].end + delta)


NEXT_OUTSIDE_WINDOW_CASES: Final = {
    "candles-at-end": _next_edit("candles", 0),
    "candles-after-end": _next_edit("candles", 1),
    "open_interest-at-end": _next_edit("open_interest", 0),
    "open_interest-after-end": _next_edit("open_interest", 1),
    "funding-end_inclusive+1": _next_edit("funding", 1),
}

NEXT_INSIDE_WINDOW_CASES: Final = {
    "candles-end-1": _next_edit("candles", -1),
    "open_interest-end-1": _next_edit("open_interest", -1),
    "funding-at-end_inclusive": _next_edit("funding", 0),
    **{f"{kind}-last+1": Edit(e.first, ("next",), _last_time(e.first) + 1) for kind, e in ENDPOINTS.items()},
}


@pytest.mark.parametrize("case", _params(NEXT_OUTSIDE_WINDOW_CASES))
def test_next_outside_window_is_refused(case: Edit) -> None:
    _refused(case)


@pytest.mark.parametrize("case", _params(NEXT_INSIDE_WINDOW_CASES))
def test_next_inside_window_is_accepted(case: Edit) -> None:
    assert _accepted(case).next == case.value


@pytest.mark.parametrize("kind", ENDPOINTS)
def test_next_with_no_rows_is_refused(kind: str) -> None:
    e = ENDPOINTS[kind]
    _refused(Edit(e.first, (e.rows,), []))


# --- the one translation: the SE-3 row constructor -------------------------------------------------------------------


def _refusing_row(*args: object) -> NoReturn:
    raise EvaluationTypeError("refused by the row constructor")


@pytest.mark.parametrize(
    ("kind", "row_class"), [("candles", "Candle"), ("open_interest", "OpenInterest"), ("funding", "FundingRate")]
)
def test_row_constructor_refusal_is_protocol_error(kind: str, row_class: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(decoding, row_class, _refusing_row)
    with pytest.raises(QuasarProtocolError) as info:
        decode(ENDPOINTS[kind].example)
    assert type(info.value) is QuasarProtocolError
    assert type(info.value.__cause__) is EvaluationTypeError
