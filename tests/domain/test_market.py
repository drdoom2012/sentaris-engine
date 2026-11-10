import copy
import itertools
import pickle
from dataclasses import FrozenInstanceError
from decimal import Decimal
from typing import Any, cast

import pytest

from sentaris_engine.domain.market import Candle, CandleSeries, Snapshot

FIVE_MINUTES = 300_000
NUMBER_FIELDS = ("open", "high", "low", "close", "volume")


class DecimalSubclass(Decimal):
    pass


def make_candle(open_time_ms: int = 0, **overrides: Any) -> Candle:
    fields: dict[str, Any] = {
        "open_time_ms": open_time_ms,
        "open": Decimal("1.5"),
        "high": Decimal(2),
        "low": Decimal(1),
        "close": Decimal("1.75"),
        "volume": Decimal(10),
        "turnover": Decimal("17.5"),
        "conflicted": False,
    }
    fields.update(overrides)
    return Candle(**fields)


def candles_at(*open_times: int) -> tuple[Candle, ...]:
    return tuple(make_candle(t) for t in open_times)


def test_candle_keeps_decimal_text_exactly() -> None:
    value = Decimal("64210.123456789012345678")
    candle = make_candle(close=value)
    assert candle.close.as_tuple() == value.as_tuple()
    assert candle.close == value
    trailing = make_candle(close=Decimal("1.50"))
    assert trailing.close.as_tuple() == Decimal("1.50").as_tuple()
    assert trailing.close.as_tuple() != Decimal("1.5").as_tuple()


BAD_NUMBERS: tuple[tuple[str, Any], ...] = (
    ("float", 1.5),
    ("int", 1),
    ("bool", True),
    ("str", "1.5"),
    ("none", None),
    ("nan", Decimal("NaN")),
    ("snan", Decimal("sNaN")),
    ("infinity", Decimal("Infinity")),
    ("negative-infinity", Decimal("-Infinity")),
    ("decimal-subclass", DecimalSubclass("1.5")),
)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        pytest.param(field, value, id=f"{field}-{label}")
        for field in (*NUMBER_FIELDS, "turnover")
        for label, value in BAD_NUMBERS
        if not (field == "turnover" and value is None)
    ],
)
def test_candle_rejects_non_decimal_and_non_finite_values(field: str, value: Any) -> None:
    with pytest.raises(ValueError, match=field):
        make_candle(**{field: value})


@pytest.mark.parametrize("value", ["no", 0, 1, None], ids=repr)
def test_candle_rejects_non_bool_conflicted(value: Any) -> None:
    with pytest.raises(ValueError, match="conflicted"):
        make_candle(conflicted=value)


@pytest.mark.parametrize("value", [True, 1.0, "0", None], ids=repr)
def test_candle_rejects_bad_open_time(value: Any) -> None:
    with pytest.raises(ValueError, match="open_time_ms"):
        make_candle(open_time_ms=value)


def test_candle_accepts_null_turnover_only() -> None:
    assert make_candle(turnover=None).turnover is None
    with pytest.raises(ValueError, match="open"):
        make_candle(open=None)


def test_candle_carries_conflicted_and_unrelated_numbers_as_given() -> None:
    candle = make_candle(high=Decimal(1), low=Decimal(9), conflicted=True)
    assert candle.conflicted is True
    assert candle.high == Decimal(1)
    assert candle.low == Decimal(9)
    assert make_candle(open=Decimal("-0")).open.is_signed()


def test_series_sorts_shuffled_input_to_the_same_series() -> None:
    ordered = candles_at(0, 300_000, 600_000, 900_000)
    expected = CandleSeries.of(FIVE_MINUTES, ordered)
    assert expected.candles == ordered
    permutations = list(itertools.permutations(ordered))
    assert len(permutations) == 24
    for permutation in permutations:
        assert CandleSeries.of(FIVE_MINUTES, permutation) == expected
    assert CandleSeries.of(FIVE_MINUTES, iter(reversed(ordered))) == expected
    assert CandleSeries.of(FIVE_MINUTES, [make_candle(5), make_candle(-5)]).candles == candles_at(-5, 5)


def test_series_rejects_duplicate_open_time() -> None:
    first = make_candle(300_000, close=Decimal(1))
    second = make_candle(300_000, close=Decimal(2))
    with pytest.raises(ValueError, match="duplicate"):
        CandleSeries.of(FIVE_MINUTES, [first, make_candle(0), second])
    with pytest.raises(ValueError):
        CandleSeries.of(FIVE_MINUTES, [first, first])
    with pytest.raises(ValueError):
        CandleSeries(FIVE_MINUTES, (first, second))


def test_direct_construction_rejects_unsorted_candles() -> None:
    with pytest.raises(ValueError, match="ascending"):
        CandleSeries(FIVE_MINUTES, candles_at(300_000, 0))
    with pytest.raises(ValueError, match="ascending"):
        CandleSeries(FIVE_MINUTES, candles_at(0, 600_000, 300_000))
    assert CandleSeries(FIVE_MINUTES, candles_at(0, 300_000)).candles == candles_at(0, 300_000)


def test_series_rejects_bad_candles_and_timeframe() -> None:
    with pytest.raises(ValueError, match="tuple"):
        CandleSeries(FIVE_MINUTES, cast(Any, [make_candle()]))
    with pytest.raises(ValueError, match="Candle"):
        CandleSeries(FIVE_MINUTES, cast(Any, (make_candle(), "x")))
    with pytest.raises(ValueError, match="Candle"):
        CandleSeries.of(FIVE_MINUTES, cast(Any, [{"open_time_ms": 0}]))
    for bad in (0, -1, True, 1.5, "5m", None):
        with pytest.raises(ValueError, match="timeframe_ms"):
            CandleSeries(cast(Any, bad), ())
        with pytest.raises(ValueError, match="timeframe_ms"):
            CandleSeries.of(cast(Any, bad), [])


def test_empty_series_and_empty_snapshot_are_valid() -> None:
    series = CandleSeries.of(FIVE_MINUTES, [])
    assert series.candles == ()
    assert series == CandleSeries(FIVE_MINUTES, ())
    snapshot = Snapshot.of([])
    assert snapshot.series == ()
    assert snapshot == Snapshot(())
    assert snapshot.series_for(FIVE_MINUTES) is None
    assert Snapshot.of([series]).series_for(3_600_000) is None
    assert Snapshot.of([series]).series_for(FIVE_MINUTES) == series


def test_snapshot_sorts_series_and_rejects_duplicate_timeframes() -> None:
    five = CandleSeries.of(300_000, candles_at(0))
    hour = CandleSeries.of(3_600_000, candles_at(0))
    day = CandleSeries.of(86_400_000, [])
    expected = Snapshot((five, hour, day))
    for permutation in itertools.permutations((five, hour, day)):
        assert Snapshot.of(permutation) == expected
    assert expected.series_for(3_600_000) is hour
    with pytest.raises(ValueError, match="duplicate"):
        Snapshot.of([five, hour, CandleSeries.of(300_000, [])])
    with pytest.raises(ValueError, match="ascending"):
        Snapshot((hour, five))
    with pytest.raises(ValueError, match="ascending"):
        Snapshot((five, five))
    with pytest.raises(ValueError, match="tuple"):
        Snapshot(cast(Any, [five]))
    with pytest.raises(ValueError, match="CandleSeries"):
        Snapshot(cast(Any, (five, "x")))


def test_snapshot_is_immutable() -> None:
    candle = make_candle()
    series = CandleSeries.of(FIVE_MINUTES, [candle])
    snapshot = Snapshot.of([series])
    assert type(series.candles) is tuple
    assert type(snapshot.series) is tuple
    with pytest.raises(FrozenInstanceError):
        cast(Any, snapshot).series = ()
    with pytest.raises(FrozenInstanceError):
        cast(Any, series).candles = ()
    with pytest.raises(FrozenInstanceError):
        cast(Any, series).timeframe_ms = 1
    with pytest.raises(FrozenInstanceError):
        cast(Any, candle).close = Decimal(9)
    with pytest.raises(TypeError):
        cast(Any, snapshot.series)[0] = series
    assert not hasattr(snapshot, "__dict__")
    source = [candle]
    built = CandleSeries.of(FIVE_MINUTES, source)
    source.append(make_candle(300_000))
    assert built.candles == (candle,)


def test_snapshot_copy_and_pickle_round_trip() -> None:
    snapshot = Snapshot.of(
        [
            CandleSeries.of(FIVE_MINUTES, [make_candle(0, close=Decimal("1.50")), make_candle(300_000, turnover=None)]),
            CandleSeries.of(3_600_000, []),
        ]
    )
    for clone in (copy.copy(snapshot), copy.deepcopy(snapshot), pickle.loads(pickle.dumps(snapshot))):
        assert type(clone) is Snapshot
        assert clone == snapshot
        assert hash(clone) == hash(snapshot)
        series = clone.series_for(FIVE_MINUTES)
        assert series is not None
        assert series.candles[0].close.as_tuple() == Decimal("1.50").as_tuple()
        assert series.candles[1].turnover is None
    candle = make_candle(conflicted=True)
    assert pickle.loads(pickle.dumps(candle)) == candle
    assert copy.deepcopy(candle) == candle
