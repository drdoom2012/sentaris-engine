"""Input kinds, needs, declarations and their combination (domain section 6.9; SE-7a spec 5.1 to 5.3, 5.6, 5.7)."""

import dataclasses
import itertools
from enum import Enum, IntEnum

import pytest

from sentaris_engine.domain.declaration import Declaration, InputKind, InputNeed, requirements, union
from sentaris_engine.domain.errors import EvaluationTypeError
from tests.domain.evaluation_helpers import raises_exactly

H = 3_600_000
MAX = 2**53 - 1

CANDLES = InputKind.CANDLES
OPEN_INTEREST = InputKind.OPEN_INTEREST
FUNDING = InputKind.FUNDING


class _IntMember(IntEnum):
    HOUR = H


def _candles(series: int, lookback: int) -> InputNeed:
    return InputNeed(CANDLES, series, lookback)


def _funding(lookback: int) -> InputNeed:
    return InputNeed(FUNDING, None, lookback)


def _decl(*needs: InputNeed) -> Declaration:
    return Declaration(needs)


def test_input_kind_has_exactly_the_section_5_inputs() -> None:
    assert [m.name for m in InputKind] == ["CANDLES", "OPEN_INTEREST", "FUNDING"]
    assert type(InputKind.CANDLES) is InputKind
    assert InputKind.CANDLES != "candles"  # type: ignore[comparison-overlap]
    assert InputKind.CANDLES != 0  # type: ignore[comparison-overlap]
    assert InputKind.__mro__ == (InputKind, Enum, object)


_BAD_DURATIONS = [
    pytest.param(True, id="bool"),
    pytest.param(_IntMember.HOUR, id="int-enum"),
    pytest.param(0, id="zero"),
    pytest.param(-1, id="negative"),
    pytest.param(2**53, id="2^53"),
    pytest.param(1.0, id="float"),
]

_MALFORMED_NEEDS = [
    pytest.param("candles", H, H, id="input-str"),
    pytest.param(0, H, H, id="input-int"),
    pytest.param(None, H, H, id="input-None"),
    *[
        pytest.param(kind, bad.values[0], H, id=f"{kind.name}-series-{bad.id}")
        for kind in (CANDLES, OPEN_INTEREST)
        for bad in _BAD_DURATIONS
    ],
    *[
        pytest.param(kind, series, bad.values[0], id=f"{kind.name}-lookback-{bad.id}")
        for kind in (CANDLES, OPEN_INTEREST, FUNDING)
        for bad in _BAD_DURATIONS
        for series in [None if kind is FUNDING else H]
    ],
    pytest.param(CANDLES, None, H, id="CANDLES-series-None"),
    pytest.param(OPEN_INTEREST, None, H, id="OPEN_INTEREST-series-None"),
    pytest.param(FUNDING, H, H, id="FUNDING-series-duration"),
    pytest.param(FUNDING, 0, H, id="FUNDING-series-zero"),
]


@pytest.mark.parametrize(("kind", "series", "lookback"), _MALFORMED_NEEDS)
def test_input_need_refuses_malformed_fields(kind: object, series: object, lookback: object) -> None:
    raises_exactly(EvaluationTypeError, lambda: InputNeed(kind, series, lookback))  # type: ignore[arg-type]


def test_input_need_accepts_boundary_durations() -> None:
    for kind in (CANDLES, OPEN_INTEREST):
        assert InputNeed(kind, 1, 1).lookback == 1
        assert InputNeed(kind, MAX, MAX).series == MAX
    assert InputNeed(FUNDING, None, 1).series is None
    assert InputNeed(FUNDING, None, MAX).lookback == MAX
    first, second = InputNeed(CANDLES, H, 2 * H), InputNeed(CANDLES, H, 2 * H)
    assert first == second
    assert hash(first) == hash(second)
    assert InputNeed(CANDLES, H, 2 * H) != InputNeed(OPEN_INTEREST, H, 2 * H)


def test_declaration_refuses_malformed_needs() -> None:
    need = _candles(H, H)
    raises_exactly(EvaluationTypeError, lambda: Declaration([need]))  # type: ignore[arg-type]
    raises_exactly(EvaluationTypeError, lambda: Declaration((need, "candles")))  # type: ignore[arg-type]
    raises_exactly(EvaluationTypeError, lambda: Declaration(((CANDLES, H, H),)))  # type: ignore[arg-type]
    raises_exactly(EvaluationTypeError, lambda: Declaration(None))  # type: ignore[arg-type]


@pytest.mark.parametrize("lookbacks", [(100 * H, 100 * H), (100 * H, 500 * H)])
def test_declaration_refuses_a_repeated_series(lookbacks: tuple[int, int]) -> None:
    first, second = lookbacks
    raises_exactly(EvaluationTypeError, lambda: Declaration((_candles(H, first), _candles(H, second))))
    raises_exactly(EvaluationTypeError, lambda: Declaration((_funding(first), _funding(second))))
    raises_exactly(
        EvaluationTypeError,
        lambda: Declaration((InputNeed(OPEN_INTEREST, H, first), InputNeed(OPEN_INTEREST, H, second))),
    )


def test_declaration_order_is_independent_of_need_order() -> None:
    c4, c1 = _candles(4 * H, H), _candles(H, H)
    oi = InputNeed(OPEN_INTEREST, 300_000, H)
    f = _funding(H)
    expected = (c1, c4, oi, f)
    declarations = [Declaration(p) for p in itertools.permutations((c4, c1, oi, f))]
    assert len(declarations) == 24
    for declaration in declarations:
        assert declaration.needs == expected
        assert type(declaration.needs) is tuple
        assert declaration == declarations[0]
        assert hash(declaration) == hash(declarations[0])
    assert Declaration(()).needs == ()


def test_the_same_period_of_two_kinds_is_two_series() -> None:
    candles, oi = _candles(H, H), InputNeed(OPEN_INTEREST, H, H)
    assert Declaration((oi, candles)).needs == (candles, oi)


def test_union_keeps_the_longest_lookback_per_series() -> None:
    assert union((_decl(_candles(H, 100 * H)), _decl(_candles(H, 500 * H)))) == _decl(_candles(H, 500 * H))
    assert union((_decl(_candles(H, 500 * H)), _decl(_candles(H, 100 * H)))).needs == (_candles(H, 500 * H),)
    assert union((_decl(_candles(H, H)), _decl(_candles(4 * H, H)))).needs == (_candles(H, H), _candles(4 * H, H))
    assert union((_decl(_candles(H, H)), _decl(_funding(8 * H)))).needs == (_candles(H, H), _funding(8 * H))
    # Equal lookbacks give one need; one declaration gives itself; funding takes the longest.
    assert union((_decl(_candles(H, 100 * H)), _decl(_candles(H, 100 * H)))) == _decl(_candles(H, 100 * H))
    single = _decl(_candles(H, 3 * H), InputNeed(OPEN_INTEREST, H, H), _funding(H))
    assert union((single,)) == single
    assert union((_decl(_funding(8 * H)), _decl(_funding(24 * H)))) == _decl(_funding(24 * H))


def test_union_is_independent_of_declaration_order() -> None:
    declarations = (
        _decl(_candles(H, 100 * H), _funding(8 * H)),
        _decl(_candles(H, 500 * H), InputNeed(OPEN_INTEREST, H, 2 * H)),
        _decl(_candles(4 * H, 10 * H), _funding(24 * H)),
        _decl(_candles(H, 300 * H)),
    )
    expected = Declaration(
        (_candles(H, 500 * H), _candles(4 * H, 10 * H), InputNeed(OPEN_INTEREST, H, 2 * H), _funding(24 * H))
    )
    results = [union(p) for p in itertools.permutations(declarations)]
    assert len(results) == 24
    for result in results:
        assert result == expected
        assert result.needs == expected.needs
    assert union(()) == Declaration(())


def test_union_refuses_malformed_input() -> None:
    d = _decl(_candles(H, H))
    raises_exactly(EvaluationTypeError, lambda: union([d]))  # type: ignore[arg-type]
    raises_exactly(EvaluationTypeError, lambda: union((_candles(H, H),)))  # type: ignore[arg-type]
    raises_exactly(EvaluationTypeError, lambda: union((None,)))  # type: ignore[arg-type]
    raises_exactly(EvaluationTypeError, lambda: union((d, None)))  # type: ignore[arg-type]
    raises_exactly(EvaluationTypeError, lambda: union(None))  # type: ignore[arg-type]


def test_requirements_are_in_code_point_key_order() -> None:
    d1, d2, d3 = _decl(_candles(H, 100 * H)), _decl(_funding(H)), _decl(_candles(H, 500 * H))
    result = requirements((("b", d1), ("a", d2), ("b", d3)))
    assert type(result) is dict
    assert list(result) == ["a", "b"]
    assert result["b"] == union((d1, d3))
    assert result["a"] == d2
    assert list(requirements((("a", d2), ("B", d1)))) == ["B", "a"]


def test_requirements_never_combine_two_instruments() -> None:
    result = requirements((("A", _decl(_candles(H, 100 * H))), ("B", _decl(_candles(H, 500 * H)))))
    assert result["A"].needs == (_candles(H, 100 * H),)
    assert result["B"].needs == (_candles(H, 500 * H),)


def test_requirements_edge_inputs() -> None:
    assert requirements(()) == {}
    d = _decl(_candles(H, H))
    same = requirements((("A", d), ("A", d)))
    assert list(same) == ["A"]
    assert same["A"] == d
    declared = (("A", d),)
    first = requirements(declared)
    first["X"] = d
    first.pop("A")
    second = requirements(declared)
    assert second == {"A": d}
    assert second is not first
    assert requirements(()) is not requirements(())


class _KeySub(str):
    pass


@pytest.mark.parametrize(
    "bad",
    [
        pytest.param([("A", Declaration(()))], id="list"),
        pytest.param((["A", Declaration(())],), id="element-list"),
        pytest.param((("A",),), id="length-one"),
        pytest.param((("A", Declaration(()), 1),), id="length-three"),
        pytest.param((("", Declaration(())),), id="empty-key"),
        pytest.param(((1, Declaration(())),), id="int-key"),
        pytest.param(((_KeySub("A"), Declaration(())),), id="str-subclass-key"),
        pytest.param((("A", None),), id="none-value"),
        pytest.param((("A", InputNeed(FUNDING, None, H)),), id="need-value"),
        pytest.param((("A", Declaration(())), None), id="none-element"),
        pytest.param(None, id="none"),
    ],
)
def test_requirements_refuse_malformed_input(bad: object) -> None:
    raises_exactly(EvaluationTypeError, lambda: requirements(bad))  # type: ignore[arg-type]


def test_new_types_are_final_and_immutable_declaration() -> None:
    def sub_need() -> None:
        class Sub(InputNeed):  # type: ignore[misc]
            pass

    def sub_declaration() -> None:
        class Sub(Declaration):  # type: ignore[misc]
            pass

    def sub_kind() -> None:
        class Sub(InputKind):  # type: ignore[misc]
            pass

    raises_exactly(TypeError, sub_need)
    raises_exactly(TypeError, sub_declaration)
    raises_exactly(TypeError, sub_kind)
    need = _candles(H, H)
    declaration = Declaration((need,))
    raises_exactly(dataclasses.FrozenInstanceError, lambda: setattr(need, "lookback", 2 * H))
    raises_exactly(dataclasses.FrozenInstanceError, lambda: setattr(declaration, "needs", ()))
    assert not hasattr(need, "__dict__")
    assert not hasattr(declaration, "__dict__")
