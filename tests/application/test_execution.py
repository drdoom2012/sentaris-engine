"""Execution over pairs: N1 to N11 and Review Focus 1 to 5 of the SE-5 specification (section 6.7)."""

import itertools
from abc import ABCMeta
from collections.abc import Callable
from functools import partial
from types import MappingProxyType
from typing import Any, NoReturn

import pytest

from sentaris_engine.application.execution import (
    ExecutionRefusedError,
    ExecutionReport,
    FaultCause,
    Pair,
    ReportEntry,
    StrategyFault,
    execute,
    qualified_type_name,
)
from sentaris_engine.domain.context import EvaluationContext
from sentaris_engine.domain.errors import EvaluationTypeError
from sentaris_engine.domain.evaluation import NotAnOutcome
from sentaris_engine.domain.payload import FrozenMapping
from sentaris_engine.domain.result import EvaluationFailure, NoSignal, Result, Signals
from sentaris_engine.domain.signal import Signal
from sentaris_engine.domain.snapshot import Snapshot
from sentaris_engine.domain.strategy import (
    StatefulStrategy,
    StatelessStrategy,
    StateTransition,
    StrategyIdentity,
    _ContractMeta,
)
from tests.application import type_name_cases
from tests.application.execution_helpers import Call, RecordingStrategy, instrument_of, params
from tests.domain.row_builders import snapshot

AS_OF = 10_000_000
SENTINEL = "sentinel-9f2c"


def _identity(id_: str, version: str = "1") -> StrategyIdentity:
    return StrategyIdentity(id_, version)


def _snapshots(*instruments: str) -> dict[str, Snapshot]:
    return {instrument: snapshot(AS_OF) for instrument in instruments}


def _triples(report: ExecutionReport) -> list[tuple[str, str, str]]:
    return [(entry.instrument, entry.strategy.id, entry.strategy.version) for entry in report.entries]


def _alone(pair: Pair, snapshots: dict[str, Snapshot]) -> ReportEntry:
    """The single entry of executing `pair` alone, with only its instrument's snapshot."""
    [entry] = execute(AS_OF, (pair,), {pair.instrument: snapshots[pair.instrument]}).entries
    return entry


def _refused(fn: Callable[[], object]) -> BaseException:
    """Call `fn` once; assert it raised exactly `ExecutionRefusedError` and return that object for its chaining."""
    with pytest.raises(BaseException) as info:
        fn()
    assert type(info.value) is ExecutionRefusedError
    return info.value


def _refused_unchained(fn: Callable[[], object]) -> None:
    """Refused with `ExecutionRefusedError`, raised `from None` (SE-5 spec 5.4)."""
    error = _refused(fn)
    assert error.__cause__ is None
    assert error.__suppress_context__ is True


# N1


def test_pairs_run_in_code_point_order() -> None:
    log: list[Call] = []
    s1 = RecordingStrategy(_identity("s", "1"), log)
    s2 = RecordingStrategy(_identity("s", "2"), log)
    r9 = RecordingStrategy(_identity("r", "9"), log)
    pairs = (
        Pair("A", s1, params()),
        Pair("A", s2, params()),
        Pair("A", r9, params()),
        Pair("B", r9, params()),
    )
    triples = [("A", "s", "1"), ("A", "s", "2"), ("A", "r", "9"), ("B", "r", "9")]
    expected = [("A", "r", "9"), ("A", "s", "1"), ("A", "s", "2"), ("B", "r", "9")]
    assert sorted(triples) == expected
    snap_a, snap_b = snapshot(AS_OF), snapshot(AS_OF)
    reports: list[ExecutionReport] = []
    for snapshots in ({"A": snap_a, "B": snap_b}, {"B": snap_b, "A": snap_a}):
        for permutation in itertools.permutations(pairs):
            log.clear()
            report = execute(AS_OF, permutation, snapshots)
            assert _triples(report) == sorted(triples)
            calls = [(identity, instrument_of(context, snapshots)) for identity, context in log]
            assert calls == [(entry.strategy, entry.instrument) for entry in report.entries]
            reports.append(report)
    assert len(reports) == 48
    for report in reports:
        assert report == reports[0]

    log.clear()
    keys = ("\U00010000", "\uffff", "a", "B")
    strategy = RecordingStrategy(_identity("s"), log)
    snapshots = _snapshots(*keys)
    report = execute(AS_OF, tuple(Pair(key, strategy, params()) for key in keys), snapshots)
    assert [entry.instrument for entry in report.entries] == ["B", "a", "\uffff", "\U00010000"]
    assert [instrument_of(context, snapshots) for _, context in log] == ["B", "a", "\uffff", "\U00010000"]


# N2


def test_duplicate_pair_is_refused() -> None:
    log: list[Call] = []
    same = RecordingStrategy(_identity("s"), log)
    _refused_unchained(lambda: execute(AS_OF, (Pair("A", same, params()), Pair("A", same, params(2))), _snapshots("A")))
    assert log == []
    first = RecordingStrategy(_identity("s"), log)
    second = RecordingStrategy(_identity("s"), log)
    _refused_unchained(
        lambda: execute(AS_OF, (Pair("A", first, params()), Pair("A", second, params())), _snapshots("A"))
    )
    assert log == []

    report = execute(AS_OF, (Pair("A", first, params()), Pair("B", second, params())), _snapshots("A", "B"))
    assert _triples(report) == [("A", "s", "1"), ("B", "s", "1")]
    report = execute(AS_OF, (Pair("A", same, params()), Pair("B", same, params())), _snapshots("A", "B"))
    assert _triples(report) == [("A", "s", "1"), ("B", "s", "1")]
    v1 = RecordingStrategy(_identity("s", "1"), log)
    v2 = RecordingStrategy(_identity("s", "2"), log)
    report = execute(AS_OF, (Pair("A", v2, params()), Pair("A", v1, params())), _snapshots("A"))
    assert _triples(report) == [("A", "s", "1"), ("A", "s", "2")]
    assert [entry.outcome for entry in report.entries] == [NoSignal(), NoSignal()]


# N3


class _WrongStateful(StatefulStrategy):
    def __init__(self) -> None:
        self.identity_reads = 0

    @property
    def identity(self) -> StrategyIdentity:
        self.identity_reads += 1
        return _identity("w")

    def evaluate(self, context: EvaluationContext, previous_state: object) -> StateTransition:
        raise AssertionError("evaluated")


class _Plain:
    def __init__(self) -> None:
        self.identity_reads = 0

    @property
    def identity(self) -> StrategyIdentity:
        self.identity_reads += 1
        return _identity("w")

    def evaluate(self, context: EvaluationContext) -> Result:
        raise AssertionError("evaluated")


class _ClaimsStateless(_Plain):
    @property  # type: ignore[misc]
    def __class__(self) -> type:
        return StatelessStrategy


def _both_instance() -> Any:
    """An object of a class holding both roots, made by bypassing `_ContractMeta.__new__` (SE-4 F2)."""

    def init(self: Any) -> None:
        self.identity_reads = 0

    def identity(self: Any) -> StrategyIdentity:
        self.identity_reads += 1
        return _identity("w")

    def evaluate(self: Any, *args: object) -> NoReturn:
        raise AssertionError("evaluated")

    namespace = {"__init__": init, "identity": property(identity), "evaluate": evaluate}
    both = ABCMeta.__new__(_ContractMeta, "Both", (StatelessStrategy, StatefulStrategy), namespace)
    return both()


def test_strategy_of_wrong_contract_is_refused() -> None:
    wrong: list[Any] = [_WrongStateful(), _Plain(), _ClaimsStateless(), _both_instance(), RecordingStrategy]
    for strategy in wrong:
        for wrong_key in ("B", "D"):  # the wrong pair sorts in the middle, then last
            log: list[Call] = []
            before = RecordingStrategy(_identity("a"), log)
            after = RecordingStrategy(_identity("z"), log)
            pairs = (
                Pair("A", before, params()),
                Pair("C", after, params()),
                Pair(wrong_key, strategy, params()),
            )
            _refused_unchained(partial(execute, AS_OF, pairs, _snapshots("A", "C", wrong_key)))
            assert log == []
            assert before.identity_reads == 0
            assert after.identity_reads == 0
            if strategy is not RecordingStrategy:
                assert strategy.identity_reads == 0

    class EqMeta(_ContractMeta):
        def __eq__(cls, other: object) -> bool:
            raise AssertionError("metaclass __eq__")

        def __hash__(cls) -> int:
            raise AssertionError("metaclass __hash__")

    class Guarded(RecordingStrategy, metaclass=EqMeta):
        pass

    log = []
    guarded = Guarded(_identity("g"), log)
    report = execute(AS_OF, (Pair("A", guarded, params()), Pair("B", guarded, params())), _snapshots("A", "B"))
    assert _triples(report) == [("A", "g", "1"), ("B", "g", "1")]
    assert len(log) == 2
    assert guarded.identity_reads == 1


# N4, Review Focus 5


class _IdentityReturns(StatelessStrategy):
    """Its `identity` returns `value` as given (anything); `evaluate` logs."""

    def __init__(self, value: object, log: list[Call]) -> None:
        self.value = value
        self.log = log

    @property
    def identity(self) -> StrategyIdentity:
        return self.value  # type: ignore[return-value]

    def evaluate(self, context: EvaluationContext) -> Result:
        self.log.append((_identity("x"), context))
        return NoSignal()


class _IdentityRaises(StatelessStrategy):
    def __init__(self, exc: BaseException, log: list[Call]) -> None:
        self.exc = exc
        self.log = log

    @property
    def identity(self) -> StrategyIdentity:
        raise self.exc

    def evaluate(self, context: EvaluationContext) -> Result:
        self.log.append((_identity("x"), context))
        return NoSignal()


class _MutatesIdentity(StatelessStrategy):
    """Returns the same `StrategyIdentity` object on every read and sets its `id` to "zzz" in `evaluate`."""

    def __init__(self, log: list[Call]) -> None:
        self.held = _identity("m")
        self.log = log

    @property
    def identity(self) -> StrategyIdentity:
        return self.held

    def evaluate(self, context: EvaluationContext) -> Result:
        self.log.append((self.held, context))
        object.__setattr__(self.held, "id", "zzz")
        return NoSignal()


class _ClaimsIdentity:
    @property  # type: ignore[misc]
    def __class__(self) -> type:
        return StrategyIdentity


class _StrSub(str):
    pass


def _mutated_identity(value: object) -> StrategyIdentity:
    identity = _identity("x")
    object.__setattr__(identity, "id", value)
    return identity


def test_identity_is_read_once_and_checked() -> None:
    log: list[Call] = []
    many = RecordingStrategy(_identity("m"), log)
    one = RecordingStrategy(_identity("o"), log)
    pairs = (
        Pair("A", many, params()),
        Pair("B", many, params()),
        Pair("C", one, params()),
        Pair("C", many, params()),
    )
    snapshots = _snapshots("A", "B", "C")
    first = execute(AS_OF, pairs, snapshots)
    assert many.identity_reads == 1
    assert one.identity_reads == 1
    assert many.read_log_lengths == [0]
    assert one.read_log_lengths == [0]
    assert len(log) == 4
    second = execute(AS_OF, pairs, snapshots)
    assert many.identity_reads == 2
    assert one.identity_reads == 2
    assert many.read_log_lengths == [0, 4]
    assert second == first

    log = []
    cause = ValueError(SENTINEL)
    raising = _IdentityRaises(cause, log)
    error = _refused(lambda: execute(AS_OF, (Pair("A", raising, params()),), _snapshots("A")))
    assert error.__cause__ is cause
    assert log == []

    bad_values: list[object] = [
        None,
        ("id", "1"),
        _ClaimsIdentity(),
        _mutated_identity(""),
        _mutated_identity(1),
        _mutated_identity(_StrSub("x")),
    ]
    for value in bad_values:
        bad = _IdentityReturns(value, log)
        valid = RecordingStrategy(_identity("v"), log)
        bad_pairs = (Pair("A", valid, params()), Pair("B", bad, params()))
        _refused_unchained(partial(execute, AS_OF, bad_pairs, _snapshots("A", "B")))
        assert log == []
    for slot in ("id", "version"):
        deleted = _identity("x")
        object.__delattr__(deleted, slot)
        deleted_pairs = (Pair("A", _IdentityReturns(deleted, log), params()),)
        _refused_unchained(partial(execute, AS_OF, deleted_pairs, _snapshots("A")))
        assert log == []
    bad_version = _identity("x")
    object.__setattr__(bad_version, "version", "")
    _refused_unchained(
        lambda: execute(AS_OF, (Pair("A", _IdentityReturns(bad_version, log), params()),), _snapshots("A"))
    )
    assert log == []

    mutating = _MutatesIdentity(log)
    other = RecordingStrategy(_identity("n"), log)
    report = execute(
        AS_OF,
        (Pair("B", mutating, params()), Pair("A", other, params()), Pair("A", mutating, params())),
        _snapshots("A", "B"),
    )
    assert _triples(report) == [("A", "m", "1"), ("A", "n", "1"), ("B", "m", "1")]
    assert report.entries[0].strategy == _identity("m")
    assert report.entries[2].strategy == _identity("m")
    assert mutating.held.id == "zzz"

    class Unhashable(RecordingStrategy):
        def __eq__(self, other: object) -> bool:
            raise AssertionError("strategy compared")

        def __hash__(self) -> int:
            raise AssertionError("strategy hashed")

    log = []
    unhashable = Unhashable(_identity("u"), log)
    report = execute(AS_OF, (Pair("A", unhashable, params()), Pair("B", unhashable, params())), _snapshots("A", "B"))
    assert unhashable.identity_reads == 1
    assert _triples(report) == [("A", "u", "1"), ("B", "u", "1")]
    assert len(log) == 2

    interrupt = KeyboardInterrupt()
    log = []
    with pytest.raises(BaseException) as info:
        execute(AS_OF, (Pair("A", _IdentityRaises(interrupt, log), params()),), _snapshots("A"))
    assert info.value is interrupt
    assert log == []


# N5


def test_snapshot_mismatch_is_refused() -> None:
    log: list[Call] = []
    s = RecordingStrategy(_identity("s"), log)
    t = RecordingStrategy(_identity("t"), log)
    pairs = (Pair("A", s, params()), Pair("B", t, params()))
    snap_a, snap_b = snapshot(AS_OF), snapshot(AS_OF)

    def refused(as_of: object, given_pairs: object, snapshots: object) -> None:
        _refused_unchained(partial(execute, as_of, given_pairs, snapshots))  # type: ignore[arg-type]
        assert log == []
        assert s.identity_reads == 0
        assert t.identity_reads == 0

    refused(AS_OF, pairs, {"A": snap_a})
    refused(AS_OF, pairs, {"A": snap_a, "B": snap_b, "C": snapshot(AS_OF)})
    refused(AS_OF, (), {"A": snap_a})
    refused(AS_OF, pairs, {"A": snap_a, "B": snapshot(AS_OF - 1)})
    refused(AS_OF, pairs, {"A": snap_a, "B": snap_a})
    refused(AS_OF, pairs, {"A": None, "B": snap_b})
    refused(AS_OF, pairs, MappingProxyType({"A": snap_a, "B": snap_b}))
    refused(AS_OF, pairs, {"A": snap_a, "B": snap_b, "": snapshot(AS_OF)})
    refused(AS_OF, pairs, {"A": snap_a, "B": snap_b, 1: snapshot(AS_OF)})

    class ArmedKey(str):
        armed = False

        def __hash__(self) -> int:
            if ArmedKey.armed:
                raise AssertionError("key hashed")
            return str.__hash__(self)

        def __eq__(self, other: object) -> bool:
            if ArmedKey.armed:
                raise AssertionError("key compared")
            return str.__eq__(self, other)

    hostile = {"A": snap_a, "B": snap_b, ArmedKey("C"): snapshot(AS_OF)}
    ArmedKey.armed = True
    try:
        refused(AS_OF, pairs, hostile)
    finally:
        ArmedKey.armed = False

    refused(AS_OF, list(pairs), {"A": snap_a, "B": snap_b})
    refused(AS_OF, (*pairs, None), {"A": snap_a, "B": snap_b})
    bad_instants: tuple[object, ...] = (-1, True, 2**53, 1.0)
    for as_of in bad_instants:
        refused(as_of, pairs, {"A": snap_a, "B": snap_b})

    assert execute(AS_OF, (), {}) == ExecutionReport(AS_OF, ())
    report = execute(AS_OF, pairs, {"A": snap_a, "B": snapshot(AS_OF)})
    assert _triples(report) == [("A", "s", "1"), ("B", "t", "1")]


# N6, Review Focus 3


class _SentinelError(Exception):
    pass


class _RaisesOnSnapshot(StatelessStrategy):
    """Calls `action` (which raises) for the context whose snapshot `is` `target`; otherwise returns `NoSignal()`."""

    identity = _identity("x")

    def __init__(self, target: Snapshot, action: Callable[[], NoReturn]) -> None:
        self.target = target
        self.action = action
        self.calls = 0

    def evaluate(self, context: EvaluationContext) -> Result:
        self.calls += 1
        if context.snapshot is self.target:
            self.action()
        return NoSignal()


def _raise(exc: BaseException) -> Callable[[], NoReturn]:
    def action() -> NoReturn:
        raise exc

    return action


def _recurse() -> NoReturn:
    _recurse()


@pytest.mark.parametrize(
    "case", ["ValueError", "EvaluationTypeError", "RecursionError", "subclass", "ExecutionRefusedError", "hostile"]
)
def test_strategy_exception_is_isolated_to_its_pair(case: str) -> None:
    class Hostile(Exception):
        def __str__(self) -> str:
            raise AssertionError("exception str")

        def __repr__(self) -> str:
            raise AssertionError("exception repr")

        def __getattribute__(self, name: str) -> Any:
            raise AssertionError("exception attribute read")

    action: Callable[[], NoReturn]
    if case == "RecursionError":
        action, expected = _recurse, "builtins.RecursionError"
    else:
        exceptions: dict[str, Exception] = {
            "ValueError": ValueError(SENTINEL),
            "EvaluationTypeError": EvaluationTypeError(SENTINEL),
            "subclass": _SentinelError(SENTINEL),
            "ExecutionRefusedError": ExecutionRefusedError(SENTINEL),
            "hostile": Hostile(SENTINEL),
        }
        exc = exceptions[case]
        action, expected = _raise(exc), qualified_type_name(type(exc))
    if case == "ValueError":
        assert expected == "builtins.ValueError"
    if case == "EvaluationTypeError":
        assert expected == "sentaris_engine.domain.errors.EvaluationTypeError"

    snapshots = _snapshots("A", "B")
    raiser = _RaisesOnSnapshot(snapshots["A"], action)
    log: list[Call] = []
    quiet = RecordingStrategy(_identity("n"), log)
    pairs = (Pair("A", raiser, params()), Pair("B", raiser, params()), Pair("A", quiet, params()))
    report = execute(AS_OF, pairs, snapshots)
    assert _triples(report) == [("A", "n", "1"), ("A", "x", "1"), ("B", "x", "1")]
    assert raiser.calls == 2
    assert report.entries[1].outcome == StrategyFault(FaultCause.RAISED, expected)
    assert type(report.entries[1].outcome) is StrategyFault
    assert report.entries[0] == _alone(pairs[2], snapshots)
    assert report.entries[2] == _alone(pairs[1], snapshots)
    assert report.entries[2].outcome == NoSignal()
    for item in (report, *report.entries, *(entry.outcome for entry in report.entries)):
        assert SENTINEL not in repr(item)
    for entry in report.entries:
        assert SENTINEL not in entry.instrument
        assert SENTINEL not in entry.strategy.id
        assert SENTINEL not in entry.strategy.version
    assert SENTINEL not in report.entries[1].outcome.type_name


# N7


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param(None, "builtins.NoneType", id="None"),
        pytest.param(Signal("k", FrozenMapping({})), qualified_type_name(Signal), id="Signal"),
        pytest.param([], "builtins.list", id="list"),
        pytest.param(NoSignal, "builtins.type", id="NoSignal-class"),
        pytest.param(NotAnOutcome(int), qualified_type_name(NotAnOutcome), id="NotAnOutcome"),
        pytest.param(ValueError(), "builtins.ValueError", id="returned-ValueError"),
        pytest.param(KeyboardInterrupt(), "builtins.KeyboardInterrupt", id="returned-KeyboardInterrupt"),
    ],
)
def test_non_outcome_is_reported_as_fault(value: object, expected: str) -> None:
    assert expected == qualified_type_name(type(value))
    assert expected != "builtins.int"
    log: list[Call] = []
    report = execute(AS_OF, (Pair("A", RecordingStrategy(_identity("s"), log, value), params()),), _snapshots("A"))
    [entry] = report.entries
    assert entry.outcome == StrategyFault(FaultCause.RETURNED_NON_OUTCOME, expected)
    assert type(entry.outcome) is StrategyFault
    assert len(log) == 1


# N8


class _DirectBase(BaseException):
    pass


@pytest.mark.parametrize(
    "exc",
    [
        pytest.param(KeyboardInterrupt(), id="KeyboardInterrupt"),
        pytest.param(SystemExit(3), id="SystemExit"),
        pytest.param(GeneratorExit(), id="GeneratorExit"),
        pytest.param(_DirectBase(), id="direct-BaseException-subclass"),
    ],
)
def test_non_ordinary_exception_propagates(exc: BaseException) -> None:
    first_log: list[Call] = []
    later_log: list[Call] = []
    raising = RecordingStrategy(_identity("a"), first_log, exc, raises=True)
    later = RecordingStrategy(_identity("b"), later_log)
    pairs = (Pair("A", later, params()), Pair("A", raising, params()))
    with pytest.raises(BaseException) as info:
        execute(AS_OF, pairs, _snapshots("A"))
    assert info.value is exc
    assert exc.__cause__ is None
    assert exc.__context__ is None
    assert len(first_log) == 1
    assert later_log == []


# N9


_TYPE_NAME_CASES = [
    pytest.param(cls, expected, log, base is Exception, id=f"{base.__name__}-{case_id}")
    for base in (Exception, object)
    for case_id, cls, expected, log in type_name_cases.type_name_cases(base)
]


@pytest.mark.parametrize(("cls", "expected", "log", "raised"), _TYPE_NAME_CASES)
def test_type_names_through_execute(cls: type, expected: str, log: list[str], raised: bool) -> None:
    calls: list[Call] = []
    if raised:
        strategy = RecordingStrategy(_identity("s"), calls, cls(), raises=True)
        cause = FaultCause.RAISED
    else:
        value = None if cls is type(None) else object.__new__(cls)
        strategy = RecordingStrategy(_identity("s"), calls, value)
        cause = FaultCause.RETURNED_NON_OUTCOME
    report = execute(AS_OF, (Pair("A", strategy, params()),), _snapshots("A"))
    assert type(report) is ExecutionReport
    [entry] = report.entries
    assert entry.outcome == StrategyFault(cause, expected)
    assert len(calls) == 1
    assert log == []


# N10


def test_context_per_pair() -> None:
    log: list[Call] = []
    p, q, r = params(1), params(2), params(3)
    first = RecordingStrategy(_identity("p"), log)
    second = RecordingStrategy(_identity("q"), log)
    third = RecordingStrategy(_identity("r"), log)
    snapshots = _snapshots("A", "B")
    expected = {_identity("p"): ("A", p), _identity("q"): ("A", q), _identity("r"): ("B", r)}
    execute(AS_OF, (Pair("B", third, r), Pair("A", second, q), Pair("A", first, p)), snapshots)
    assert len(log) == 3
    for identity, context in log:
        instrument, parameters = expected[identity]
        assert context.snapshot is snapshots[instrument]
        assert context.parameters is parameters
        assert context.as_of == AS_OF
        fields: tuple[object, ...] = (
            context.snapshot,
            context.parameters,
            context.as_of,
            context.snapshot.as_of,
            context.snapshot.candles,
            context.snapshot.open_interest,
            context.snapshot.funding,
        )
        for value in fields:
            for key in ("A", "B"):
                assert value is not key
                assert value != key
    a_contexts = [context for identity, context in log if identity != _identity("r")]
    assert a_contexts[0].snapshot is a_contexts[1].snapshot


# N11


def test_entry_is_the_same_alone_and_together() -> None:
    log: list[Call] = []
    signals = Signals((Signal("k", FrozenMapping({"v": 1})),))
    pairs = (
        Pair("B", RecordingStrategy(_identity("signals"), log, signals), params(1)),
        Pair("A", RecordingStrategy(_identity("none"), log, NoSignal()), params(2)),
        Pair("B", RecordingStrategy(_identity("failure"), log, EvaluationFailure("f")), params(3)),
        Pair("A", RecordingStrategy(_identity("raises"), log, ValueError(), raises=True), params(4)),
        Pair("A", RecordingStrategy(_identity("non-outcome"), log, None), params(5)),
    )
    snapshots = _snapshots("A", "B")
    mixed = execute(AS_OF, pairs, snapshots)
    assert len(mixed.entries) == 5
    by_key = {(entry.instrument, entry.strategy): entry for entry in mixed.entries}
    for pair in pairs:
        alone = _alone(pair, snapshots)
        assert by_key[(alone.instrument, alone.strategy)] == alone
    assert execute(AS_OF, pairs, snapshots) == mixed


# Review Focus 4


def test_outcome_is_reported_as_the_very_object() -> None:
    log: list[Call] = []
    signals = Signals(tuple(Signal(kind, FrozenMapping({})) for kind in ("c", "a", "b")))
    no_signal = NoSignal()
    failure = EvaluationFailure("f")
    pairs = (
        Pair("A", RecordingStrategy(_identity("1"), log, signals), params()),
        Pair("A", RecordingStrategy(_identity("2"), log, no_signal), params()),
        Pair("A", RecordingStrategy(_identity("3"), log, failure), params()),
    )
    report = execute(AS_OF, pairs, _snapshots("A"))
    assert report.entries[0].outcome is signals
    assert report.entries[1].outcome is no_signal
    assert report.entries[2].outcome is failure
    assert [signal.kind for signal in signals.signals] == ["c", "a", "b"]


# Review Focus 1, R2, R5


class _ChangesSnapshots(StatelessStrategy):
    """In `evaluate`, deletes "B" from the caller's dict and inserts a surplus "C"."""

    identity = _identity("a")

    def __init__(self, snapshots: dict[str, Snapshot]) -> None:
        self.snapshots = snapshots

    def evaluate(self, context: EvaluationContext) -> Result:
        del self.snapshots["B"]
        self.snapshots["C"] = snapshot(AS_OF)
        return NoSignal()


class _ChangesPair(StatelessStrategy):
    """In `evaluate`, sets every field of `target` to another valid value with `object.__setattr__`."""

    identity = _identity("a")

    def __init__(self, target: Pair, replacement: StatelessStrategy) -> None:
        self.target = target
        self.replacement = replacement

    def evaluate(self, context: EvaluationContext) -> Result:
        object.__setattr__(self.target, "instrument", "A")
        object.__setattr__(self.target, "parameters", params(99))
        object.__setattr__(self.target, "strategy", self.replacement)
        return NoSignal()


def test_snapshots_dict_changed_during_run_changes_nothing() -> None:
    log: list[Call] = []
    snapshots = _snapshots("A", "B")
    snap_b = snapshots["B"]
    later = RecordingStrategy(_identity("b"), log)
    pairs = (Pair("B", later, params()), Pair("A", _ChangesSnapshots(snapshots), params()))
    report = execute(AS_OF, pairs, snapshots)
    assert _triples(report) == [("A", "a", "1"), ("B", "b", "1")]
    assert set(snapshots) == {"A", "C"}
    [(_, context)] = log
    assert context.snapshot is snap_b

    log = []
    snapshots = _snapshots("A", "B")
    parameters = params(7)
    later = RecordingStrategy(_identity("b"), log)
    later_pair = Pair("B", later, parameters)
    replacement_log: list[Call] = []
    replacement = RecordingStrategy(_identity("z"), replacement_log)
    changer = _ChangesPair(later_pair, replacement)
    report = execute(AS_OF, (later_pair, Pair("A", changer, params())), snapshots)
    assert later_pair.instrument == "A"
    assert _triples(report) == [("A", "a", "1"), ("B", "b", "1")]
    assert replacement_log == []
    [(_, context)] = log
    assert context.snapshot is snapshots["B"]
    assert context.parameters is parameters
