from dataclasses import fields
from decimal import Decimal
from types import MappingProxyType

import pytest

from sentaris_engine.domain.market import Candle
from sentaris_engine.infrastructure.quasar.client import MAX_PAGE_LIMIT, MAX_WINDOW_SLOTS, QuasarClient
from sentaris_engine.infrastructure.quasar.errors import (
    ContractViolationError,
    NotReadyError,
    QuasarUnavailableError,
    UnexpectedResponseError,
    UnknownSeriesError,
)
from sentaris_engine.infrastructure.quasar.pages import PageRequest
from tests.support.quasar_fixtures import FIVE_MINUTES, candle_json, encode, error_body, page_json
from tests.support.quasar_stub import ScriptedResponse, StubQuasar

VENUE = "binance-usdm"
SYMBOL = "BTC/USDT:USDT"
T0 = 1792643400000
JSON = MappingProxyType({"Content-Type": "application/json"})


def slot(index: int) -> int:
    return T0 + index * FIVE_MINUTES


def run(count: int, *, step: int = 1) -> list[dict[str, object]]:
    """`count` candles at slots 0, step, 2·step, ..., each with a distinct close so a repeat or a loss shows."""
    return [candle_json(slot(index * step), close=str(index + 1)) for index in range(count)]


def at(*indexes: int) -> list[dict[str, object]]:
    return [candle_json(slot(index), close=str(index + 1)) for index in indexes]


def read(stub: StubQuasar, slots: int, *, first: int = 0) -> object:
    client = QuasarClient(stub.base_url)
    return client.read_candles(VENUE, SYMBOL, "5m", slot(first), slot(first + slots))


def key(candle: Candle) -> tuple[int, tuple[object, ...], bool]:
    return candle.open_time_ms, candle.close.as_tuple(), candle.conflicted


def keys_of(stored: list[dict[str, object]]) -> list[tuple[int, tuple[object, ...], bool]]:
    return [(int(str(c["open_time_ms"])), Decimal(str(c["close"])).as_tuple(), c["conflicted"] is True) for c in stored]


def windows(stub: StubQuasar) -> list[tuple[int, int]]:
    return [(int(r.query["start"][0]), int(r.query["end"][0])) for r in stub.requests]


def test_exactly_full_last_page_needs_no_extra_request(stub: StubQuasar) -> None:
    stored = run(2000)
    stub.add_series(VENUE, SYMBOL, FIVE_MINUTES, stored)
    result = QuasarClient(stub.base_url).read_candles(VENUE, SYMBOL, "5m", slot(0), slot(2000))
    assert [len(page.candles) for page in result.pages] == [1000, 1000]
    assert result.pages[0].next_start == slot(1000)
    assert result.pages[1].next_start is None
    assert len(stub.requests) == 2
    assert [key(c) for c in result.candles] == keys_of(stored)
    times = [c.open_time_ms for c in result.candles]
    assert times == sorted(set(times))


def test_page_boundary_loses_and_repeats_nothing(stub: StubQuasar) -> None:
    stored = run(2500)
    stub.add_series(VENUE, SYMBOL, FIVE_MINUTES, stored)
    result = QuasarClient(stub.base_url).read_candles(VENUE, SYMBOL, "5m", slot(0), slot(2500))
    assert [len(page.candles) for page in result.pages] == [1000, 1000, 500]
    assert [key(c) for c in result.candles] == keys_of(stored)
    first_next = result.pages[0].next_start
    assert first_next is not None
    assert int(stub.requests[1].query["start"][0]) == first_next
    assert {r.query["end"][0] for r in stub.requests} == {str(slot(2500))}
    assert {r.query["limit"][0] for r in stub.requests} == {str(MAX_PAGE_LIMIT)}


def test_gaps_are_not_filled(stub: StubQuasar) -> None:
    stored = run(1500, step=3)  # a candle at every third slot: two pages, holes inside and across the page boundary
    stub.add_series(VENUE, SYMBOL, FIVE_MINUTES, stored)
    result = QuasarClient(stub.base_url).read_candles(VENUE, SYMBOL, "5m", slot(0), slot(4500))
    assert [len(page.candles) for page in result.pages] == [1000, 500]
    assert [key(c) for c in result.candles] == keys_of(stored)  # exactly the stored ones, in order, none repeated
    for page in result.pages:
        assert page.coverage.missing_slots > 0
        assert page.coverage.gap_free is False
    assert [page.coverage.slots for page in result.pages] == [3000, 1500]
    assert [page.coverage.missing_slots for page in result.pages] == [2000, 1000]


def test_empty_window_of_an_existing_series(stub: StubQuasar) -> None:
    stub.add_series(VENUE, SYMBOL, FIVE_MINUTES, at(0, 1, 2))  # stored, but nothing inside the window below
    result = QuasarClient(stub.base_url).read_candles(VENUE, SYMBOL, "5m", slot(100), slot(110))
    assert len(stub.requests) == 1
    assert result.candles == ()
    assert len(result.pages) == 1
    assert result.pages[0].coverage.slots == 10
    assert result.pages[0].coverage.missing_slots == 10
    # a series that does not exist is not an empty window
    with pytest.raises(UnknownSeriesError):
        QuasarClient(stub.base_url).read_candles(VENUE, "NOPE", "5m", slot(100), slot(110))


def test_conflicted_candle_is_kept_with_its_first_value(stub: StubQuasar) -> None:
    stored = [candle_json(slot(0)), candle_json(slot(1), close="123.45", conflicted=True), candle_json(slot(2))]
    stub.add_series(VENUE, SYMBOL, FIVE_MINUTES, stored)
    result = QuasarClient(stub.base_url).read_candles(VENUE, SYMBOL, "5m", slot(0), slot(3))
    flagged = result.candles[1]
    assert flagged.conflicted is True
    assert flagged.close.as_tuple() == Decimal("123.45").as_tuple()
    assert [c.conflicted for c in result.candles] == [False, True, False]
    assert result.pages[0].coverage.conflicted_slots == 1
    assert result.pages[0].coverage.gap_free is False


def test_window_over_10000_slots_is_split_into_chunks(stub: StubQuasar) -> None:
    indexes = [0, 9999, 10000, 19999, 20000, 24999]
    stored = at(*indexes)
    stub.add_series(VENUE, SYMBOL, FIVE_MINUTES, stored)
    result = QuasarClient(stub.base_url).read_candles(VENUE, SYMBOL, "5m", slot(0), slot(25000))
    assert windows(stub) == [(slot(0), slot(10000)), (slot(10000), slot(20000)), (slot(20000), slot(25000))]
    assert all(end - start <= MAX_WINDOW_SLOTS * FIVE_MINUTES for start, end in windows(stub))
    assert [key(c) for c in result.candles] == keys_of(stored)
    assert [c.open_time_ms for c in result.candles] == [slot(i) for i in indexes]
    assert (result.start, result.end) == (slot(0), slot(25000))


def test_chunk_of_exactly_10000_slots_is_one_request(stub: StubQuasar) -> None:
    stub.add_series(VENUE, SYMBOL, FIVE_MINUTES, at(0, 9999))
    result = QuasarClient(stub.base_url).read_candles(VENUE, SYMBOL, "5m", slot(0), slot(10000))
    assert windows(stub) == [(slot(0), slot(10000))]
    assert len(result.pages) == 1
    assert len(result.candles) == 2


def test_window_of_10001_slots_is_two_requests(stub: StubQuasar) -> None:
    stub.add_series(VENUE, SYMBOL, FIVE_MINUTES, at(0, 10000))
    result = QuasarClient(stub.base_url).read_candles(VENUE, SYMBOL, "5m", slot(0), slot(10001))
    assert windows(stub) == [(slot(0), slot(10000)), (slot(10000), slot(10001))]
    assert [c.open_time_ms for c in result.candles] == [slot(0), slot(10000)]


def scripted_page(stub: StubQuasar, candles: list[dict[str, object]], next_start: int | None) -> None:
    """The first request is answered with a page that carries `candles` and the given `next`, whatever is stored."""
    request = PageRequest(VENUE, SYMBOL, "5m", FIVE_MINUTES, slot(0), slot(100), MAX_PAGE_LIMIT)
    body = encode(page_json(request, candles, oldest=slot(0), newest=slot(99), next_start=next_start))
    stub.script(ScriptedResponse(200, body, JSON))


@pytest.mark.parametrize(
    ("candle_indexes", "next_index"),
    [
        pytest.param((0, 1, 2), 2, id="next-equals-last-candle"),
        pytest.param((0, 1, 2), 100, id="next-at-end"),
        pytest.param((), 50, id="next-without-candles"),
        pytest.param((0,), 2, id="next-on-a-page-that-is-not-full"),
    ],
)
def test_non_advancing_next_ends_in_an_error_after_one_request(
    stub: StubQuasar, candle_indexes: tuple[int, ...], next_index: int
) -> None:
    stub.add_series(VENUE, SYMBOL, FIVE_MINUTES, at(0, 1, 2))
    scripted_page(stub, at(*candle_indexes), slot(next_index))
    with pytest.raises(ContractViolationError):
        QuasarClient(stub.base_url).read_candles(VENUE, SYMBOL, "5m", slot(0), slot(100))
    assert len(stub.requests) == 1


def failure_cases() -> list[tuple[str, ScriptedResponse, type[Exception]]]:
    return [
        ("not-ready", ScriptedResponse(503, error_body("not_ready"), JSON), NotReadyError),
        (
            "truncated",
            ScriptedResponse(200, b'{"venue": "binance', JSON, declared_length=5000),
            QuasarUnavailableError,
        ),
        ("proxy-502", ScriptedResponse(502, b"<html>Bad Gateway</html>"), UnexpectedResponseError),
    ]


@pytest.mark.parametrize(("failure", "error"), [pytest.param(f, e, id=name) for name, f, e in failure_cases()])
def test_failure_midway_returns_nothing(stub: StubQuasar, failure: ScriptedResponse, error: type[Exception]) -> None:
    stub.add_series(VENUE, SYMBOL, FIVE_MINUTES, run(2500))
    stub.script(failure, after=1)
    result: object = None
    with pytest.raises(error):
        result = read(stub, 2500)
    assert result is None
    assert len(stub.requests) == 2


def test_failure_on_the_second_chunk_returns_nothing(stub: StubQuasar) -> None:
    stub.add_series(VENUE, SYMBOL, FIVE_MINUTES, at(0, 5, 10000, 10005))
    stub.script(ScriptedResponse(404, error_body("unknown_series", "gone"), JSON), after=1)
    result: object = None
    with pytest.raises(UnknownSeriesError):
        result = read(stub, 20000)
    assert result is None
    assert len(stub.requests) == 2


@pytest.mark.parametrize(
    ("start", "end"),
    [
        pytest.param(slot(10), slot(10), id="start-equals-end"),
        pytest.param(slot(11), slot(10), id="start-after-end"),
        pytest.param(slot(0), slot(15000) + 1, id="unaligned-end-over-10000-slots"),
        pytest.param(slot(0) + 1, slot(15000), id="unaligned-start-over-10000-slots"),
        pytest.param(946684800000 - FIVE_MINUTES, slot(0), id="start-before-quasar-range"),
        pytest.param(slot(0), 4102444800000 + 2 * FIVE_MINUTES, id="end-after-quasar-range"),
    ],
)
def test_preconditions_send_nothing(stub: StubQuasar, start: int, end: int) -> None:
    stub.add_series(VENUE, SYMBOL, FIVE_MINUTES, at(0, 1))
    with pytest.raises(ValueError):
        QuasarClient(stub.base_url).read_candles(VENUE, SYMBOL, "5m", start, end)
    assert stub.requests == []


def test_read_is_deterministic_on_unchanged_data(stub: StubQuasar) -> None:
    stub.add_series(VENUE, SYMBOL, FIVE_MINUTES, run(1500, step=2))
    client = QuasarClient(stub.base_url)
    first = client.read_candles(VENUE, SYMBOL, "5m", slot(0), slot(3000))
    second = client.read_candles(VENUE, SYMBOL, "5m", slot(0), slot(3000))
    assert first == second
    assert len(first.pages) == 2


def test_pages_of_one_read_may_come_from_different_moments(stub: StubQuasar) -> None:
    """Pins that SE-4 makes NO consistency claim across the pages of one read.

    A candle backfilled before the cursor after the first page was served is absent from the result, and nothing in
    the result says so. Detecting or preventing this is OD-24, to be decided with replay, and this test is replaced by
    that decision.
    """
    stored = run(1500, step=2)  # open times at even slots; the backfilled one is at an odd slot
    stub.add_series(VENUE, SYMBOL, FIVE_MINUTES, stored)
    backfilled = candle_json(slot(1), close="999")

    backfills: list[int] = []

    def backfill(index: int) -> None:
        if index == 1:
            stored.append(backfilled)
            backfills.append(index)

    stub.on_request = backfill
    client = QuasarClient(stub.base_url)
    result = client.read_candles(VENUE, SYMBOL, "5m", slot(0), slot(3000))
    assert backfills == [1]  # the backfill happened between the first and the second page
    assert len(stub.requests) == 2
    assert [len(page.candles) for page in result.pages] == [1000, 500]
    assert result.pages[0].candles[1].open_time_ms == slot(2)  # the first page is the old one
    assert result.pages[0].coverage.missing_slots == 1000  # as stated at the first moment: 1000 of 2000 slots
    assert slot(1) not in [c.open_time_ms for c in result.candles]
    assert [field.name for field in fields(result)] == ["start", "end", "pages"]  # nothing says the pages differ
    # the backfilled candle is stored now: a fresh read of the same window contains it and differs from the first
    fresh = client.read_candles(VENUE, SYMBOL, "5m", slot(0), slot(3000))
    assert slot(1) in [c.open_time_ms for c in fresh.candles]
    assert fresh != result
