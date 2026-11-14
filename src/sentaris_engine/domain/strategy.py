"""Strategy identity, the two contracts, absent state and the stateful outcome (domain sections 6.4, 6.8, 6.9; SE-4 spec 5.1 to 5.3, 5.5; SE-7a spec 5.4)."""

from abc import ABCMeta, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar, Final, NoReturn, Self, final

from sentaris_engine.domain.context import EvaluationContext
from sentaris_engine.domain.declaration import Declaration
from sentaris_engine.domain.errors import EvaluationTypeError
from sentaris_engine.domain.parameters import Parameters
from sentaris_engine.domain.result import EvaluationFailure, NoSignal, Result, Signals


@final
@dataclass(frozen=True, slots=True)
class StrategyIdentity:
    """The `id` and `version` of a strategy; no format is imposed (section 6.4, SE-4 spec 5.1)."""

    id: str
    version: str

    def __post_init__(self) -> None:
        if type(self.id) is not str or not self.id:
            raise EvaluationTypeError("strategy id is not a non-empty exact str")
        if type(self.version) is not str or not self.version:
            raise EvaluationTypeError("strategy version is not a non-empty exact str")

    def __init_subclass__(cls, **kwargs: object) -> None:
        raise TypeError("StrategyIdentity cannot be subclassed")


class _ContractMeta(ABCMeta):
    """Makes membership of a contract real inheritance and a strategy's contract unique (SE-4 spec 5.2)."""

    _roots: ClassVar[tuple[type, ...]] = ()

    def register(cls, subclass: type) -> NoReturn:
        raise TypeError("a contract takes no virtual subclass")

    def __new__(
        mcls,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, object],
        contract: bool = False,
        **kwargs: object,
    ) -> "_ContractMeta":
        created = super().__new__(mcls, name, bases, namespace, **kwargs)
        held = sum(1 for base in created.__mro__ for root in mcls._roots if base is root)
        if contract:
            if held or len(mcls._roots) >= 2:
                raise TypeError("only the two engine contracts are roots")
            mcls._roots = mcls._roots + (created,)
        elif held >= 2:
            raise TypeError("a strategy follows exactly one contract")
        return created


class StatelessStrategy(metaclass=_ContractMeta, contract=True):
    """A pure transition from the context to a result (DR-26, DR-22, DR-12); it never receives the instrument key (section 6.8)."""

    @property
    @abstractmethod
    def identity(self) -> StrategyIdentity: ...

    @abstractmethod
    def evaluate(self, context: EvaluationContext) -> Result: ...

    @abstractmethod
    def declare(self, parameters: Parameters) -> Declaration | EvaluationFailure:
        """The inputs this strategy needs for `parameters` alone, or a failure when it cannot form them (section 6.9, section 6.8)."""


class StatefulStrategy(metaclass=_ContractMeta, contract=True):
    """A pure transition from the context and the previous state to a result and the next state (DR-26, DR-22, DR-12, section 6.8)."""

    @property
    @abstractmethod
    def identity(self) -> StrategyIdentity: ...

    @abstractmethod
    def evaluate(self, context: EvaluationContext, previous_state: object) -> "StateTransition": ...

    @abstractmethod
    def declare(self, parameters: Parameters) -> Declaration | EvaluationFailure:
        """The inputs this strategy needs for `parameters` alone, or a failure when it cannot form them (section 6.9, section 6.8)."""


@final
class NoState:
    """The single marker of absent state, distinct from every state value (DR-25, SE-4 spec 5.3, U1, U2)."""

    __slots__ = ()
    _instance: ClassVar["NoState | None"] = None

    def __new__(cls) -> Self:
        if NoState._instance is None:
            NoState._instance = super().__new__(cls)
        return NoState._instance

    def __init_subclass__(cls, **kwargs: object) -> None:
        raise TypeError("NoState cannot be subclassed")

    def __copy__(self) -> Self:
        return self

    def __deepcopy__(self, memo: dict[int, object]) -> Self:
        return self


NO_STATE: Final = NoState()


@final
@dataclass(frozen=True, slots=True, eq=False)
class StateTransition:
    """The outcome of a stateful evaluation; the state is held as given and never inspected (DR-25, U2, OD-19)."""

    result: Result
    next_state: object = field(repr=False)  # opaque state is never inspected (DR-25)

    def __post_init__(self) -> None:
        result_type = type(self.result)
        if result_type is not Signals and result_type is not NoSignal and result_type is not EvaluationFailure:
            raise EvaluationTypeError("result is not exactly one of the three outcomes")

    def __init_subclass__(cls, **kwargs: object) -> None:
        raise TypeError("StateTransition cannot be subclassed")
