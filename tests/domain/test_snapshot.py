"""The snapshot: shape, order, nothing after `as_of` and key order (SE-3 spec 5.7, section 6; N7, N8, N11, N13).

Order, shape and key-order cases use `as_of = 10_000_000`, so that they cannot be refused by the `as_of` check instead.
"""

import dataclasses
from collections.abc import Callable
from types import MappingProxyType

import pytest

from sentaris_engine.domain.errors import EvaluationTypeError
from sentaris_engine.domain.snapshot import Snapshot
from sentaris_engine.domain.timing import MAX_TIME_MS
from tests.domain.evaluation_helpers import raises_exactly
from tests.domain.row_builders import candle, funding, open_interest, snapshot, snapshot_with

_MINUTE = 60_000

# Series field -> (builder of its row, builder of the other series' row).
_SERIES: dict[str, tuple[Callable[[int], object], Callable[[int], object]]] = {
    "candles": (candle, open_interest),
    "open_interest": (open_interest, candle),
}


# --- N7 (DR-10) ---


_T = 1_000

# (field, valid value, the same value with one element changed)
_ORDER_CASES: list[object] = [
    *(
        pytest.param(field, {_MINUTE: (row(0), row(_MINUTE))}, {_MINUTE: invalid}, id=f"{field}-{case_id}")
        for field, (row, _) in _SERIES.items()
        for case_id, invalid in (("duplicate", (row(0), row(0))), ("descending", (row(_MINUTE), row(0))))
    ),
    pytest.param(
        "funding",
        (funding(_T, "Regular"), funding(_T, "Special")),
        (funding(_T, "Regular"), funding(_T, "Regular")),
        id="funding-duplicate",
    ),
    pytest.param(
        "funding",
        (funding(_T, "Regular"), funding(_T, "Special")),
        (funding(_T, "Special"), funding(_T, "Regular")),
        id="funding-rate-type-descending",
    ),
    pytest.param("funding", (funding(0), funding(_T)), (funding(_T), funding(0)), id="funding-time-descending"),
]


@pytest.mark.parametrize(("field", "valid", "invalid"), _ORDER_CASES)
def test_unordered_or_duplicate_series_is_refused(field: str, valid: object, invalid: object) -> None:
    held = snapshot_with(field, valid)
    assert getattr(held, field) == valid
    raises_exactly(EvaluationTypeError, lambda: snapshot_with(field, invalid))


# --- N8 (U1; DR-01 closed part, DR-02, DR-04 settled part) ---


def test_row_after_as_of_is_refused() -> None:
    as_of = 1_000_000
    candles = (candle(820_000), candle(880_000))
    boundary_candle = candle(940_000)
    late_candle = candle(940_001)
    snapshot(as_of, candles={_MINUTE: (*candles, boundary_candle)})
    raises_exactly(EvaluationTypeError, lambda: snapshot(as_of, candles={_MINUTE: (*candles, late_candle)}))

    interest = (open_interest(0), open_interest(500_000))
    boundary_interest = open_interest(1_000_000)
    late_interest = open_interest(1_000_001)
    snapshot(as_of, open_interest={_MINUTE: (*interest, boundary_interest)})
    raises_exactly(
        EvaluationTypeError,
        lambda: snapshot(as_of, open_interest={_MINUTE: (*interest, late_interest)}),
    )

    settled = (funding(0), funding(500_000))
    boundary_funding = funding(1_000_000)
    late_funding = funding(1_000_001)
    snapshot(as_of, funding=(*settled, boundary_funding))
    raises_exactly(EvaluationTypeError, lambda: snapshot(as_of, funding=(*settled, late_funding)))


def test_candle_boundary_at_max_time() -> None:
    last_closed = candle(MAX_TIME_MS - _MINUTE)
    held = snapshot(MAX_TIME_MS, candles={_MINUTE: (last_closed,)})
    assert held.candles[_MINUTE] == (last_closed,)
    open_at_max = candle(MAX_TIME_MS)
    open_at_one = candle(1)
    raises_exactly(EvaluationTypeError, lambda: snapshot(MAX_TIME_MS, candles={1: (open_at_max,)}))
    raises_exactly(EvaluationTypeError, lambda: snapshot(MAX_TIME_MS, candles={MAX_TIME_MS: (open_at_one,)}))


# --- N11 (SE-3 spec 5.7) ---


def _series_cases(field: str) -> list[object]:
    row, other = _SERIES[field]
    valid_series = {_MINUTE: (row(0),)}
    cases: list[tuple[str, object, object]] = [
        ("key-zero", {_MINUTE: ()}, {0: ()}),
        ("key-negative", {_MINUTE: ()}, {-1: ()}),
        ("key-True", {_MINUTE: ()}, {True: ()}),
        ("key-str", {_MINUTE: ()}, {"5m": ()}),
        ("source-MappingProxyType", {}, MappingProxyType({})),
        ("source-pairs", {}, [(_MINUTE, ())]),
        ("series-list", {_MINUTE: ()}, {_MINUTE: []}),
        ("element-other-row", valid_series, {_MINUTE: (other(0),)}),
        ("element-tuple", valid_series, {_MINUTE: ((row(0),),)}),
        ("element-dict", valid_series, {_MINUTE: ({},)}),
        ("element-list", valid_series, {_MINUTE: ([],)}),
        ("element-None", valid_series, {_MINUTE: (None,)}),
        ("value-dict-of-series", valid_series, {_MINUTE: valid_series}),
    ]
    return [pytest.param(field, valid, invalid, id=f"{field}-{case_id}") for case_id, valid, invalid in cases]


_SHAPE_CASES: list[object] = [
    pytest.param("as_of", 10_000_000, -1, id="as_of-negative"),
    pytest.param("as_of", 10_000_000, True, id="as_of-True"),
    *_series_cases("candles"),
    *_series_cases("open_interest"),
    pytest.param("funding", (), [], id="funding-list"),
    pytest.param("funding", (), {}, id="funding-dict"),
]


@pytest.mark.parametrize(("field", "valid", "invalid"), _SHAPE_CASES)
def test_invalid_snapshot_shape_is_refused(field: str, valid: object, invalid: object) -> None:
    snapshot_with(field, valid)
    raises_exactly(EvaluationTypeError, lambda: snapshot_with(field, invalid))


def test_absent_and_empty_inputs() -> None:
    t = 10_000_000
    absent = Snapshot(t, {}, {}, None)
    assert dict(absent.candles) == {}
    assert dict(absent.open_interest) == {}
    assert absent.funding is None
    empty = Snapshot(t, {_MINUTE: ()}, {300_000: ()}, ())
    assert empty.candles[_MINUTE] == ()
    assert empty.open_interest[300_000] == ()
    assert empty.funding == ()


# --- N13 (DR-10) ---


@pytest.mark.parametrize(
    "source",
    [
        pytest.param({300_000: (), 60_000: (), 3_600_000: ()}, id="mixed"),
        pytest.param({3_600_000: (), 300_000: (), 60_000: ()}, id="descending"),
        pytest.param({3_600_000: (), 60_000: (), 300_000: ()}, id="shuffled"),
    ],
)
def test_snapshot_mappings_iterate_in_key_order(source: dict[int, tuple[()]]) -> None:
    expected = [60_000, 300_000, 3_600_000]
    held = snapshot(candles=dict(source), open_interest=dict(source))
    for mapping in (held.candles, held.open_interest):
        assert list(mapping) == expected
        assert list(mapping.keys()) == expected
        assert [key for key, _ in mapping.items()] == expected


def test_snapshot_replace_is_refused() -> None:
    snap = snapshot()
    # The stored mappings are MappingProxyType, which the constructor refuses (N11): fails closed by design.
    raises_exactly(EvaluationTypeError, lambda: dataclasses.replace(snap, as_of=snap.as_of))
