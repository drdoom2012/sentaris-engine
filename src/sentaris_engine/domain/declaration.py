"""Input kinds, needs, declarations and their combination (domain section 6.9; SE-7a spec 5.1 to 5.3, 5.6, 5.7)."""

from dataclasses import dataclass
from enum import Enum
from typing import Final, final

from sentaris_engine.domain.errors import EvaluationTypeError
from sentaris_engine.domain.instrument import check_instrument_key
from sentaris_engine.domain.timing import check_duration


@final
class InputKind(Enum):
    """One engine input of section 5; not a signal kind (DR-23). The values are read by nothing (plan R1)."""

    CANDLES = "candles"
    OPEN_INTEREST = "open_interest"
    FUNDING = "funding"


# The canonical order of spec 5.3: members are not orderable (plan R2).
_RANK: Final[dict[InputKind, int]] = {InputKind.CANDLES: 0, InputKind.OPEN_INTEREST: 1, InputKind.FUNDING: 2}


@final
@dataclass(frozen=True, slots=True)
class InputNeed:
    """One input over one lookback: the timeframe (candles) or period (open interest) is the series; funding has none (spec 5.2)."""

    input: InputKind
    series: int | None
    lookback: int

    def __post_init__(self) -> None:
        if type(self.input) is not InputKind:
            raise EvaluationTypeError("input is not an InputKind member")
        if self.input is InputKind.FUNDING:
            if self.series is not None:
                raise EvaluationTypeError("funding has no series")
        else:
            check_duration(self.series)
        check_duration(self.lookback)

    def __init_subclass__(cls, **kwargs: object) -> None:
        raise TypeError("InputNeed cannot be subclassed")


def _sort_key(need: InputNeed) -> tuple[int, int]:
    # Funding has one series, so 0 never collides (plan R2).
    return (_RANK[need.input], 0 if need.series is None else need.series)


@final
@dataclass(frozen=True, slots=True)
class Declaration:
    """What a strategy needs, one need per series, held in canonical order (section 6.9; DR-10)."""

    needs: tuple[InputNeed, ...]

    def __post_init__(self) -> None:
        if type(self.needs) is not tuple:
            raise EvaluationTypeError("needs is not an exact tuple")
        seen: set[tuple[InputKind, int | None]] = set()
        for need in self.needs:
            if type(need) is not InputNeed:
                raise EvaluationTypeError("a need is not an exact InputNeed")
            key = (need.input, need.series)
            if key in seen:
                raise EvaluationTypeError("a series is declared twice (section 6.9, U3)")
            seen.add(key)
        object.__setattr__(self, "needs", tuple(sorted(self.needs, key=_sort_key)))

    def __init_subclass__(cls, **kwargs: object) -> None:
        raise TypeError("Declaration cannot be subclassed")


def union(declarations: tuple[Declaration, ...]) -> Declaration:
    """One need per series that appears, with the longest lookback declared for it (section 6.9; DR-10)."""
    if type(declarations) is not tuple:
        raise EvaluationTypeError("declarations is not an exact tuple")
    for declaration in declarations:
        if type(declaration) is not Declaration:
            raise EvaluationTypeError("a declaration is not an exact Declaration")
    longest: dict[tuple[InputKind, int | None], int] = {}
    for declaration in declarations:
        for need in declaration.needs:
            key = (need.input, need.series)
            longest[key] = max(longest.get(key, 0), need.lookback)
    return Declaration(tuple(InputNeed(kind, series, lookback) for (kind, series), lookback in longest.items()))


def requirements(declared: tuple[tuple[str, Declaration], ...]) -> dict[str, Declaration]:
    """The union of the declarations of each instrument, in ascending key order; instruments never mix (sections 6.7, 6.9; DR-10)."""
    if type(declared) is not tuple:
        raise EvaluationTypeError("declared is not an exact tuple")
    for element in declared:
        if type(element) is not tuple or len(element) != 2:
            raise EvaluationTypeError("an element is not an exact pair")
        key, declaration = element
        check_instrument_key(key)
        if type(declaration) is not Declaration:
            raise EvaluationTypeError("a declaration is not an exact Declaration")
    groups: dict[str, list[Declaration]] = {}
    for key, declaration in declared:
        groups.setdefault(key, []).append(declaration)
    return {key: union(tuple(groups[key])) for key in sorted(groups)}
