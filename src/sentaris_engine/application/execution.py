"""Execution over (strategy, instrument) pairs for one `as_of` (domain section 6.7, DR-22; SE-5 spec 5).

The fault entry distinguishes a raise from a non-outcome return (U4); a reported type name is module-qualified
(U2), or the qualname alone when no usable module is recorded (U9), and is read without strategy code
(SE-4 spec 5.6).
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import final

from sentaris_engine.domain.context import EvaluationContext
from sentaris_engine.domain.errors import EvaluationTypeError
from sentaris_engine.domain.evaluation import NotAnOutcome, evaluate_stateless
from sentaris_engine.domain.instrument import check_instrument_key
from sentaris_engine.domain.parameters import Parameters
from sentaris_engine.domain.result import EvaluationFailure, NoSignal, Result, Signals
from sentaris_engine.domain.snapshot import Snapshot
from sentaris_engine.domain.strategy import StatefulStrategy, StatelessStrategy, StrategyIdentity
from sentaris_engine.domain.timing import check_instant


class ExecutionRefusedError(ValueError):
    """The whole execution is refused before any strategy is evaluated (SE-5 spec 5.4)."""


@final
@dataclass(frozen=True, slots=True, eq=False)
class Pair:
    """One strategy on one instrument with its own parameters; the strategy is held as given (SE-5 spec 5.1, U6)."""

    instrument: str
    strategy: StatelessStrategy = field(repr=False)  # never touched here: its repr is strategy code (F8)
    parameters: Parameters

    def __post_init__(self) -> None:
        check_instrument_key(self.instrument)
        if type(self.parameters) is not Parameters:
            raise EvaluationTypeError("parameters are not an exact Parameters (U6)")

    def __init_subclass__(cls, **kwargs: object) -> None:
        raise TypeError("Pair cannot be subclassed")


@final
class FaultCause(Enum):
    """Whether a strategy raised or returned a non-outcome (U4); the values are read by nothing (plan R3)."""

    RAISED = "raised"
    RETURNED_NON_OUTCOME = "returned_non_outcome"


@final
@dataclass(frozen=True, slots=True)
class StrategyFault:
    """The separate result of section 6.7: a cause and a type name, never a message or value (SE-5 spec 5.2)."""

    cause: FaultCause
    type_name: str  # may be empty (U9)

    def __post_init__(self) -> None:
        if type(self.cause) is not FaultCause:
            raise EvaluationTypeError("cause is not a FaultCause member")
        if type(self.type_name) is not str:
            raise EvaluationTypeError("type name is not an exact str")

    def __init_subclass__(cls, **kwargs: object) -> None:
        raise TypeError("StrategyFault cannot be subclassed")


type Outcome = Signals | NoSignal | EvaluationFailure | StrategyFault


@final
@dataclass(frozen=True, slots=True)
class ReportEntry:
    """The outcome of one pair, under its instrument key and the identity read for the execution (section 6.7)."""

    instrument: str
    strategy: StrategyIdentity
    outcome: Outcome

    def __post_init__(self) -> None:
        check_instrument_key(self.instrument)
        if type(self.strategy) is not StrategyIdentity:
            raise EvaluationTypeError("strategy is not an exact StrategyIdentity")
        outcome_type = type(self.outcome)
        if (
            outcome_type is not Signals
            and outcome_type is not NoSignal
            and outcome_type is not EvaluationFailure
            and outcome_type is not StrategyFault
        ):
            raise EvaluationTypeError("outcome is not exactly one of the three outcomes or a StrategyFault")

    def __init_subclass__(cls, **kwargs: object) -> None:
        raise TypeError("ReportEntry cannot be subclassed")


@final
@dataclass(frozen=True, slots=True)
class ExecutionReport:
    """One entry per pair for one `as_of`; no wall-clock time, run id or duration (DR-09)."""

    as_of: int
    entries: tuple[ReportEntry, ...]

    def __post_init__(self) -> None:
        check_instant(self.as_of)
        if type(self.entries) is not tuple:
            raise EvaluationTypeError("entries is not an exact tuple")
        for entry in self.entries:
            if type(entry) is not ReportEntry:
                raise EvaluationTypeError("entries holds an element that is not a ReportEntry")

    def __init_subclass__(cls, **kwargs: object) -> None:
        raise TypeError("ExecutionReport cannot be subclassed")


def qualified_type_name(cls: type) -> str:
    """The module-qualified name of `cls`, read through `type`'s own descriptors (U2, U9; SE-5 spec 5.5, plan R1; limitation in SE-5 spec section 9)."""
    qualname: str = str.__str__(type.__dict__["__qualname__"].__get__(cls))
    try:
        module_value: object = type.__dict__["__module__"].__get__(cls)
    except AttributeError:
        return qualname
    if not type.__subclasscheck__(str, type(module_value)):
        return qualname
    module: str = str.__str__(module_value)
    if not module:  # exact str: no subclass __len__ or __bool__ runs
        return qualname
    return module + "." + qualname


def execute(as_of: int, pairs: tuple[Pair, ...], snapshots: dict[str, Snapshot]) -> ExecutionReport:
    """Run every pair once for one `as_of`, sequentially in code-point order (section 6.7, DR-10; SE-5 spec 5.3).

    Every refused input refuses the whole execution before any strategy is evaluated (U3, U5, U8); an empty
    execution gives an empty report (U7). An `Exception` from a strategy is that pair's fault entry and nothing
    of it reaches another pair (DR-22); any other `BaseException` propagates unchanged (U1). An outcome is
    reported as the very object (DR-23). Execution works on its own copy of `snapshots` and of each pair's
    fields (plan R2, plan R5) and keeps nothing between calls.
    """
    # Step 1: shapes. Keys and values are checked before any set of keys is built (SE-5 spec 5.3).
    try:
        check_instant(as_of)
        if type(snapshots) is not dict:
            raise EvaluationTypeError("snapshots is not an exact dict")
        given: dict[str, Snapshot] = {}
        for key, value in snapshots.items():
            check_instrument_key(key)
            if type(value) is not Snapshot:
                raise EvaluationTypeError("snapshot is not an exact Snapshot")
            given[key] = value
    except EvaluationTypeError:
        raise ExecutionRefusedError("malformed as_of or snapshots") from None
    if type(pairs) is not tuple:
        raise ExecutionRefusedError("pairs is not an exact tuple") from None
    held: list[tuple[str, StatelessStrategy, Parameters]] = []
    for pair in pairs:
        if type(pair) is not Pair:
            raise ExecutionRefusedError("pairs holds an element that is not a Pair") from None
        held.append((pair.instrument, pair.strategy, pair.parameters))  # each Pair read once (plan R5)

    # Step 2: snapshots (U5, U8).
    if set(given) != {instrument for instrument, _, _ in held}:
        raise ExecutionRefusedError("snapshot keys differ from the pairs' instruments (U5)") from None
    seen: set[int] = set()
    for given_snapshot in given.values():
        if given_snapshot.as_of != as_of:
            raise ExecutionRefusedError("a snapshot's as_of differs from the execution's (U5)") from None
        if id(given_snapshot) in seen:
            raise ExecutionRefusedError("one snapshot object under two keys (U8)") from None
        seen.add(id(given_snapshot))

    # Step 3: contract, by the real MRO of the real type, compared by `is` only (U3).
    for _, strategy, _ in held:
        mro: tuple[type, ...] = type.__dict__["__mro__"].__get__(type(strategy))
        stateless = sum(1 for base in mro if base is StatelessStrategy)
        stateful = sum(1 for base in mro if base is StatefulStrategy)
        if stateless != 1 or stateful != 0:
            raise ExecutionRefusedError("a strategy does not follow exactly the stateless contract (U3)") from None

    # Step 4: identity, read once per strategy object (told apart by id()) and copied (section 6.7).
    identities: dict[int, StrategyIdentity] = {}
    for _, strategy, _ in held:
        if id(strategy) in identities:
            continue
        try:
            read: object = strategy.identity
        except Exception as exc:  # U1: only an Exception refuses; it becomes the cause (spec 5.4)
            raise ExecutionRefusedError("reading a strategy's identity raised") from exc
        if type(read) is not StrategyIdentity:
            raise ExecutionRefusedError("a strategy's identity is not an exact StrategyIdentity") from None
        try:  # a slot deleted with object.__delattr__ is a malformed field (spec 5.3 step 4)
            identity_id: object = read.id
            identity_version: object = read.version
        except AttributeError:
            raise ExecutionRefusedError("a strategy's identity lacks a field") from None
        if type(identity_id) is not str or not identity_id:
            raise ExecutionRefusedError("a strategy's identity id is not a non-empty exact str") from None
        if type(identity_version) is not str or not identity_version:
            raise ExecutionRefusedError("a strategy's identity version is not a non-empty exact str") from None
        identities[id(strategy)] = StrategyIdentity(identity_id, identity_version)

    # Steps 5 and 6: duplicates and order, on exact str only; no Pair is compared (section 6.7, DR-10).
    keys: list[tuple[str, str, str]] = []
    for instrument, strategy, _ in held:
        identity = identities[id(strategy)]
        keys.append((instrument, identity.id, identity.version))
    if len(set(keys)) != len(keys):
        raise ExecutionRefusedError("two pairs with the same instrument and identity") from None
    order = sorted(range(len(held)), key=keys.__getitem__)

    # Steps 7 and 8: evaluation, one pair after another, and the report (section 6.7, DR-22, U1).
    entries: list[ReportEntry] = []
    for index in order:
        instrument, strategy, parameters = held[index]
        context = EvaluationContext(given[instrument], parameters, as_of)
        raised: type | None = None
        try:
            returned: Result | NotAnOutcome = evaluate_stateless(strategy, context)
        except Exception as exc:  # noqa: BLE001  # U1: any other BaseException propagates unchanged
            raised = type(exc)
        outcome: Outcome
        if raised is not None:
            outcome = StrategyFault(FaultCause.RAISED, qualified_type_name(raised))
        elif type(returned) is NotAnOutcome:
            outcome = StrategyFault(FaultCause.RETURNED_NON_OUTCOME, qualified_type_name(returned.returned_type))
        else:
            outcome = returned
        entries.append(ReportEntry(instrument, identities[id(strategy)], outcome))
    return ExecutionReport(as_of, tuple(entries))
