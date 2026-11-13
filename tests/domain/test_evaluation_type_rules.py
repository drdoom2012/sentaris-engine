"""Rules over every SE-3 type: immutability, finality, exact errors (SE-3 spec 5, N10, N14, N15).

Each task adds its own test functions, named after the N-test with a suffix for its group (plan, Global Constraints).
"""

import dataclasses
from collections.abc import Callable, Mapping
from decimal import Decimal
from functools import partial
from types import MappingProxyType

import pytest

from sentaris_engine.domain.context import EvaluationContext
from sentaris_engine.domain.errors import EvaluationTypeError
from sentaris_engine.domain.instrument import check_instrument_key
from sentaris_engine.domain.parameters import Parameters
from sentaris_engine.domain.payload import FrozenMapping
from sentaris_engine.domain.result import EvaluationFailure, NoSignal, Signals
from sentaris_engine.domain.rows import Candle, FundingRate, OpenInterest
from sentaris_engine.domain.signal import Signal
from sentaris_engine.domain.snapshot import Snapshot
from sentaris_engine.domain.timing import check_duration, check_instant
from tests.domain.evaluation_helpers import UNEXPECTED_IDS, UNEXPECTED_VALUES, raises_exactly
from tests.domain.row_builders import build_with, candle, funding, open_interest, snapshot, snapshot_with

# --- Parameters and validators (Task 1) ---


def test_types_are_immutable_parameters() -> None:
    p = Parameters({"a": 1})
    raises_exactly(AttributeError, lambda: setattr(p, "_mapping", FrozenMapping({"b": 2})))
    raises_exactly(AttributeError, lambda: setattr(p, "extra", 1))
    raises_exactly(AttributeError, lambda: delattr(p, "_mapping"))
    assert not hasattr(p, "__dict__")
    assert p == Parameters({"a": 1})

    source = {"a": 1}
    from_dict = Parameters(source)
    source["a"] = 2
    source["b"] = 3
    assert from_dict == Parameters({"a": 1})
    assert len(from_dict) == 1

    pairs = [("a", 1)]
    from_pairs = Parameters(pairs)
    pairs[0] = ("a", 5)
    pairs.append(("b", 2))
    assert from_pairs == Parameters({"a": 1})
    assert len(from_pairs) == 1

    before = hash(p)
    raises_exactly(TypeError, lambda: p.__init__({"b": 2}))
    assert p == Parameters({"a": 1})
    assert hash(p) == before
    assert dict(p.items()) == {"a": 1}


def test_types_cannot_be_subclassed_parameters() -> None:
    def define() -> None:
        class _Sub(Parameters):  # type: ignore[misc]
            pass

    raises_exactly(TypeError, define)


def _cyclic_list() -> list[object]:
    cyclic: list[object] = []
    cyclic.append(cyclic)
    return cyclic


def _self_containing_pairs() -> list[object]:
    pairs: list[object] = [("a", 1)]
    pairs.append(pairs)
    return pairs


def _self_containing_dict() -> dict[str, object]:
    cyclic: dict[str, object] = {}
    cyclic["a"] = cyclic
    return cyclic


# Each case is (id, valid baseline, the same source with one element changed).
MALFORMED_PARAMETERS: list[tuple[str, object, object]] = [
    # malformed pair structures
    ("pair-one-element", [("a", 1)], [("a",)]),
    ("pair-three-elements", [("a", 1)], [("a", 1, 2)]),
    ("pair-as-list", [("a", 1)], [["a", 1]]),
    ("pair-as-str", [("a", 1)], ["a"]),
    ("second-pair-as-str", [("a", 1), ("b", 2)], [("a", 1), "b"]),
    ("pair-None", [("a", 1)], [None]),
    # unhashable keys
    ("key-list", [("a", 1)], [([1], 1)]),
    ("key-dict", [("a", 1)], [({}, 1)]),
    # cyclic values
    ("value-cyclic-list", {"a": 1}, {"a": _cyclic_list()}),
    ("pairs-containing-themselves", [("a", 1)], _self_containing_pairs()),
    ("dict-containing-itself", {"a": 1}, _self_containing_dict()),
    # nested values
    ("value-list", {"a": 1}, {"a": [1]}),
    ("value-tuple", {"a": 1}, {"a": (1,)}),
    ("value-dict", {"a": 1}, {"a": {"b": 1}}),
    ("value-set", {"a": 1}, {"a": {1}}),
    ("value-FrozenMapping", {"a": 1}, {"a": FrozenMapping({"b": 1})}),
    ("value-sNaN", {"a": Decimal(1)}, {"a": Decimal("sNaN")}),
]

# (name, callable, valid argument, ids of the UNEXPECTED_VALUES that are valid for this argument)
_TASK_1_ARGUMENTS: list[tuple[str, Callable[[object], object], object, tuple[str, ...]]] = [
    ("check_instant", check_instant, 1, ("int",)),
    ("check_duration", check_duration, 1, ("int",)),
    ("check_instrument_key", check_instrument_key, "k", ("str-number",)),
    ("Parameters", Parameters, {}, ()),
]

_TASK_1_CASES: list[object] = [
    *(
        pytest.param(Parameters, valid, invalid, id=f"Parameters-{case_id}")
        for case_id, valid, invalid in MALFORMED_PARAMETERS
    ),
    *(
        pytest.param(fn, valid, value, id=f"{name}-{value_id}")
        for name, fn, valid, skips in _TASK_1_ARGUMENTS
        for value, value_id in zip(UNEXPECTED_VALUES, UNEXPECTED_IDS, strict=True)
        if value_id not in skips
    ),
]


@pytest.mark.parametrize(("fn", "valid", "invalid"), _TASK_1_CASES)
def test_malformed_input_raises_only_evaluation_type_error_parameters(
    fn: Callable[[object], object], valid: object, invalid: object
) -> None:
    fn(valid)
    raises_exactly(EvaluationTypeError, lambda: fn(invalid))


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(value, id=value_id)
        for value, value_id in zip(UNEXPECTED_VALUES, UNEXPECTED_IDS, strict=True)
        if value_id not in ("int", "str-number")
    ],
)
def test_malformed_input_raises_only_evaluation_type_error_parameters_value(value: object) -> None:
    Parameters({"a": 1})
    raises_exactly(EvaluationTypeError, partial(Parameters, {"a": value}))


# --- Signal and Result (Task 2) ---


def _signal() -> Signal:
    return Signal("k", FrozenMapping({}))


def test_types_are_immutable_result() -> None:
    s = _signal()
    outcomes: list[tuple[object, tuple[str, ...]]] = [
        (s, ("kind", "payload")),
        (Signals((s,)), ("signals",)),
        (NoSignal(), ()),
        (EvaluationFailure("x"), ("code",)),
    ]
    extra = "extra"
    for outcome, fields in outcomes:
        assert not hasattr(outcome, "__dict__")
        assert [f.name for f in dataclasses.fields(outcome)] == list(fields)  # type: ignore[arg-type]
        # CPython's frozen slots dataclass raises TypeError, not FrozenInstanceError, for a name that is not a field.
        with pytest.raises((AttributeError, TypeError)):
            setattr(outcome, extra, 1)
        assert not hasattr(outcome, extra)
        for name in fields:
            raises_exactly(dataclasses.FrozenInstanceError, lambda o=outcome, n=name: setattr(o, n, None))  # type: ignore[misc]
            raises_exactly(dataclasses.FrozenInstanceError, lambda o=outcome, n=name: delattr(o, n))  # type: ignore[misc]
    assert type(Signals((s,)).signals) is tuple

    source = [s]
    with pytest.raises(EvaluationTypeError):
        Signals(source)  # type: ignore[arg-type]
    held = Signals(tuple(source))
    source.append(_signal())
    assert held.signals == (s,)


def test_types_cannot_be_subclassed_result() -> None:
    def subclass(base: type) -> Callable[[], None]:
        def define() -> None:
            type("_Sub", (base,), {})

        return define

    for base in (Signal, Signals, NoSignal, EvaluationFailure):
        raises_exactly(TypeError, subclass(base))


def _unexpected_cases(name: str, build: Callable[[object], object], skips: tuple[str, ...] = ()) -> list[object]:
    return [
        pytest.param(build, value, id=f"{name}-{value_id}")
        for value, value_id in zip(UNEXPECTED_VALUES, UNEXPECTED_IDS, strict=True)
        if value_id not in skips
    ]


_TASK_2_CASES: list[object] = [
    pytest.param(lambda v: Signals(((_signal(),),)), None, id="Signals-tuple-of-tuple-of-signals"),  # type: ignore[arg-type]
    *_unexpected_cases("Signal-kind", lambda v: Signal(v, FrozenMapping({})), ("str-number",)),  # type: ignore[arg-type]
    *_unexpected_cases("Signal-payload", lambda v: Signal("k", v)),  # type: ignore[arg-type]
    *_unexpected_cases("Signals-signals", lambda v: Signals(v)),  # type: ignore[arg-type]
    *_unexpected_cases("Signals-element", lambda v: Signals((v,))),  # type: ignore[arg-type]
    *_unexpected_cases("EvaluationFailure-code", lambda v: EvaluationFailure(v), ("str-number",)),  # type: ignore[arg-type]
]


@pytest.mark.parametrize(("build", "invalid"), _TASK_2_CASES)
def test_malformed_input_raises_only_evaluation_type_error_result(
    build: Callable[[object], object], invalid: object
) -> None:
    raises_exactly(EvaluationTypeError, lambda: build(invalid))


def test_valid_baselines_construct_result() -> None:
    assert Signal("1", FrozenMapping({})).kind == "1"
    assert EvaluationFailure("1").code == "1"
    assert Signals((_signal(),)).signals == (_signal(),)


# --- Rows (Task 3) ---

_ROW_FIELDS: dict[str, tuple[str, ...]] = {
    "Candle": ("open_time", "open", "high", "low", "close", "volume", "turnover", "conflicted"),
    "OpenInterest": ("time", "open_interest", "open_interest_value", "conflicted"),
    "FundingRate": ("funding_time", "rate_type", "funding_rate", "mark_price", "conflicted"),
}


def test_types_are_immutable_rows() -> None:
    rows: tuple[Candle, OpenInterest, FundingRate] = (candle(0), open_interest(0), funding(0))
    extra = "extra"
    for row in rows:
        fields = _ROW_FIELDS[type(row).__name__]
        assert not hasattr(row, "__dict__")
        assert tuple(f.name for f in dataclasses.fields(row)) == fields
        # CPython's frozen slots dataclass raises TypeError, not FrozenInstanceError, for a name that is not a field.
        with pytest.raises((AttributeError, TypeError)):
            setattr(row, extra, 1)
        assert not hasattr(row, extra)
        for name in fields:
            raises_exactly(dataclasses.FrozenInstanceError, partial(setattr, row, name, None))
            raises_exactly(dataclasses.FrozenInstanceError, partial(delattr, row, name))


def test_types_cannot_be_subclassed_rows() -> None:
    def subclass(base: type) -> Callable[[], object]:
        def define() -> object:
            return type("_Sub", (base,), {})

        return define

    for base in (Candle, OpenInterest, FundingRate):
        raises_exactly(TypeError, subclass(base))


# (row, field, valid value, ids of the UNEXPECTED_VALUES that are valid for this field)
_ROW_ARGUMENTS: list[tuple[str, str, object, tuple[str, ...]]] = [
    ("Candle", "open_time", 1, ("int",)),
    ("Candle", "open", Decimal(1), ()),
    ("Candle", "high", Decimal(1), ()),
    ("Candle", "low", Decimal(1), ()),
    ("Candle", "close", Decimal(1), ()),
    ("Candle", "volume", Decimal(1), ()),
    ("Candle", "turnover", Decimal(1), ("None",)),
    ("Candle", "conflicted", True, ()),
    ("OpenInterest", "time", 1, ("int",)),
    ("OpenInterest", "open_interest", Decimal(1), ()),
    ("OpenInterest", "open_interest_value", Decimal(1), ()),
    ("OpenInterest", "conflicted", True, ()),
    ("FundingRate", "funding_time", 1, ("int",)),
    ("FundingRate", "rate_type", "Special", ()),
    ("FundingRate", "funding_rate", Decimal(1), ()),
    ("FundingRate", "mark_price", Decimal(1), ("None",)),
    ("FundingRate", "conflicted", True, ()),
]

_ROW_CASES: list[object] = [
    pytest.param(row, field, valid, value, id=f"{row}-{field}-{value_id}")
    for row, field, valid, skips in _ROW_ARGUMENTS
    for value, value_id in zip(UNEXPECTED_VALUES, UNEXPECTED_IDS, strict=True)
    if value_id not in skips
]


@pytest.mark.parametrize(("row", "field", "valid", "invalid"), _ROW_CASES)
def test_malformed_input_raises_only_evaluation_type_error_rows(
    row: str, field: str, valid: object, invalid: object
) -> None:
    build_with(row, field, valid)
    raises_exactly(EvaluationTypeError, lambda: build_with(row, field, invalid))


# --- Snapshot and EvaluationContext (Task 4) ---

_MINUTE = 60_000


def test_types_are_immutable_snapshot() -> None:
    candles: dict[int, tuple[Candle, ...]] = {_MINUTE: (candle(0),)}
    interest: dict[int, tuple[OpenInterest, ...]] = {_MINUTE: (open_interest(0),)}
    snap = Snapshot(10_000_000, candles, interest, (funding(0),))
    context = EvaluationContext(snap, Parameters({}), snap.as_of)
    instances: list[tuple[Snapshot | EvaluationContext, tuple[str, ...]]] = [
        (snap, ("as_of", "candles", "open_interest", "funding")),
        (context, ("snapshot", "parameters", "as_of")),
    ]
    extra = "extra"
    for instance, fields in instances:
        assert not hasattr(instance, "__dict__")
        assert tuple(f.name for f in dataclasses.fields(instance)) == fields
        # CPython's frozen slots dataclass raises TypeError, not FrozenInstanceError, for a name that is not a field.
        with pytest.raises((AttributeError, TypeError)):
            setattr(instance, extra, 1)
        assert not hasattr(instance, extra)
        for name in fields:
            raises_exactly(dataclasses.FrozenInstanceError, partial(setattr, instance, name, None))
            raises_exactly(dataclasses.FrozenInstanceError, partial(delattr, instance, name))

    assert type(snap.candles) is MappingProxyType
    assert type(snap.open_interest) is MappingProxyType
    assert type(snap.funding) is tuple

    def assign_item(mapping: Mapping[int, tuple[object, ...]]) -> None:
        mapping[_MINUTE] = ()  # type: ignore[index]

    raises_exactly(TypeError, partial(assign_item, snap.candles))
    raises_exactly(TypeError, partial(assign_item, snap.open_interest))

    candles[_MINUTE] = ()
    candles[300_000] = ()
    interest.clear()
    assert dict(snap.candles) == {_MINUTE: (candle(0),)}
    assert dict(snap.open_interest) == {_MINUTE: (open_interest(0),)}
    assert context.snapshot is snap


def test_types_cannot_be_subclassed_snapshot() -> None:
    def subclass(base: type) -> Callable[[], object]:
        def define() -> object:
            return type("_Sub", (base,), {})

        return define

    for base in (Snapshot, EvaluationContext):
        raises_exactly(TypeError, subclass(base))


def _snapshot_series_with(field: str, series: object) -> object:
    return snapshot_with(field, {_MINUTE: series})


def _snapshot_element_with(field: str, element: object) -> object:
    if field == "funding":
        return snapshot_with(field, (element,))
    return snapshot_with(field, {_MINUTE: (element,)})


def _context_with(field: str, value: object) -> object:
    fields: dict[str, object] = {"snapshot": snapshot(), "parameters": Parameters({}), "as_of": 10_000_000}
    fields[field] = value
    # Values are deliberately invalid, so they are not typed against the context's fields.
    return EvaluationContext(**fields)  # type: ignore[arg-type]


# (name, build from one value, valid value, ids of the UNEXPECTED_VALUES that are valid there).
# `EvaluationContext.as_of` skips nothing: `1` differs from the baseline snapshot's `as_of`.
_SNAPSHOT_ARGUMENTS: list[tuple[str, Callable[[object], object], object, tuple[str, ...]]] = [
    ("Snapshot-as_of", partial(snapshot_with, "as_of"), 10_000_000, ("int",)),
    ("Snapshot-candles", partial(snapshot_with, "candles"), {}, ()),
    ("Snapshot-candles-series", partial(_snapshot_series_with, "candles"), (), ()),
    ("Snapshot-candles-element", partial(_snapshot_element_with, "candles"), candle(0), ()),
    ("Snapshot-open_interest", partial(snapshot_with, "open_interest"), {}, ()),
    ("Snapshot-open_interest-series", partial(_snapshot_series_with, "open_interest"), (), ()),
    ("Snapshot-open_interest-element", partial(_snapshot_element_with, "open_interest"), open_interest(0), ()),
    ("Snapshot-funding", partial(snapshot_with, "funding"), (), ("None",)),
    ("Snapshot-funding-element", partial(_snapshot_element_with, "funding"), funding(0), ()),
    ("EvaluationContext-snapshot", partial(_context_with, "snapshot"), snapshot(), ()),
    ("EvaluationContext-parameters", partial(_context_with, "parameters"), Parameters({}), ()),
    ("EvaluationContext-as_of", partial(_context_with, "as_of"), 10_000_000, ()),
]

_SNAPSHOT_CASES: list[object] = [
    pytest.param(build, valid, value, id=f"{name}-{value_id}")
    for name, build, valid, skips in _SNAPSHOT_ARGUMENTS
    for value, value_id in zip(UNEXPECTED_VALUES, UNEXPECTED_IDS, strict=True)
    if value_id not in skips
]


@pytest.mark.parametrize(("build", "valid", "invalid"), _SNAPSHOT_CASES)
def test_malformed_input_raises_only_evaluation_type_error_snapshot(
    build: Callable[[object], object], valid: object, invalid: object
) -> None:
    build(valid)
    raises_exactly(EvaluationTypeError, partial(build, invalid))
