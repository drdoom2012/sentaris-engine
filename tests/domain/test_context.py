"""The evaluation context (SE-3 spec 5.8; N9, N12)."""

import pytest

from sentaris_engine.domain.context import EvaluationContext
from sentaris_engine.domain.errors import EvaluationTypeError
from sentaris_engine.domain.parameters import Parameters
from sentaris_engine.domain.payload import FrozenMapping
from tests.domain.evaluation_helpers import raises_exactly
from tests.domain.row_builders import snapshot


def _context(**overrides: object) -> EvaluationContext:
    snap = snapshot()
    fields: dict[str, object] = {"snapshot": snap, "parameters": Parameters({}), "as_of": snap.as_of, **overrides}
    # Overrides may be deliberately invalid, so they are not typed against the context's fields.
    return EvaluationContext(**fields)  # type: ignore[arg-type]


def test_context_as_of_must_match_snapshot() -> None:
    snap = snapshot()
    held = EvaluationContext(snap, Parameters({}), snap.as_of)
    assert held.snapshot is snap
    assert held.as_of == snap.as_of
    raises_exactly(EvaluationTypeError, lambda: EvaluationContext(snap, Parameters({}), snap.as_of + 1))


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        pytest.param("parameters", {}, id="parameters-dict"),
        pytest.param("parameters", FrozenMapping({}), id="parameters-FrozenMapping"),
        pytest.param("snapshot", None, id="snapshot-None"),
        pytest.param("snapshot", object(), id="snapshot-object"),
        pytest.param("as_of", -1, id="as_of-negative"),
        pytest.param("as_of", 1.0, id="as_of-float"),
    ],
)
def test_invalid_context_field_is_refused(field: str, invalid: object) -> None:
    _context()
    raises_exactly(EvaluationTypeError, lambda: _context(**{field: invalid}))


def test_context_identity() -> None:
    # Equality and hash are by identity (SE-3 spec 5.7).
    snap = snapshot()
    first = EvaluationContext(snap, Parameters({}), snap.as_of)
    second = EvaluationContext(snap, Parameters({}), snap.as_of)
    assert first != second
    assert len({first, second}) == 2
    assert hash(first) == hash(first)
