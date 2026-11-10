import copy
import pickle
from collections.abc import Callable, Mapping
from decimal import Decimal
from typing import Any, cast

import pytest

from sentaris_engine.domain.parameters import Parameters
from sentaris_engine.domain.payload import Payload, PayloadError
from tests.support.vectors import REJECTED, REJECTED_VALUES


def test_parameters_flat_scalars_are_readable() -> None:
    parameters = Parameters.of({"n": 3, "p": Decimal("0.50"), "flag": True, "s": "x"})
    assert isinstance(parameters, Mapping)
    assert parameters["p"] == Decimal("0.50")
    assert str(parameters["p"]) == "0.50"
    assert parameters["n"] == 3
    assert parameters["flag"] is True
    assert parameters["s"] == "x"
    assert len(parameters) == 4
    assert list(parameters) == ["flag", "n", "p", "s"]
    assert "n" in parameters
    assert "missing" not in parameters
    assert parameters.get("missing") is None
    with pytest.raises(KeyError):
        parameters["missing"]


def test_parameters_default_is_empty() -> None:
    assert len(Parameters.of()) == 0
    assert Parameters.of() == Parameters.of({}) == Parameters.of([])


@pytest.mark.parametrize("value", [None, (1,), [1], {}, {"a": 1}, Payload.of({"a": 1})], ids=repr)
def test_parameters_reject_null_sequence_and_mapping(value: object) -> None:
    with pytest.raises(ValueError, match="'k'"):
        Parameters.of({"k": value})


def test_parameters_reject_null_sequence_and_mapping_in_pair_form() -> None:
    with pytest.raises(ValueError):
        Parameters.of([("a", 1), ("k", None)])
    with pytest.raises(ValueError):
        Parameters.of(Payload.of({"k": [1]}))


@pytest.mark.parametrize("build", [b for _, b in REJECTED_VALUES], ids=[n for n, _ in REJECTED_VALUES])
def test_parameters_reject_what_payloads_reject(build: Callable[[], Any]) -> None:
    with pytest.raises(PayloadError):
        Parameters.of({"k": build()})


@pytest.mark.parametrize("build", [b for _, b in REJECTED], ids=[n for n, _ in REJECTED])
def test_parameters_reject_what_payloads_reject_as_a_source(build: Callable[[], Any]) -> None:
    with pytest.raises(PayloadError):
        Parameters.of(build())


def test_parameters_reject_duplicate_pair_key() -> None:
    with pytest.raises(PayloadError):
        Parameters.of([("a", 1), ("a", 2)])


def test_parameters_accept_the_sources_payload_accepts() -> None:
    expected = Parameters.of({"a": 1, "b": Decimal("2.0")})
    assert Parameters.of([("b", Decimal("2.0")), ("a", 1)]) == expected
    assert Parameters.of((("b", Decimal("2.0")), ("a", 1))) == expected
    assert Parameters.of(Payload.of({"a": 1, "b": Decimal("2.0")})) == expected
    assert Parameters.of(Payload.of({"a": 1})) == Parameters.of({"a": 1})


def test_parameters_equality_is_canonical() -> None:
    assert Parameters.of({"a": Decimal("1.0")}) != Parameters.of({"a": Decimal("1.00")})
    assert Parameters.of({"a": 1}) != Parameters.of({"a": True})
    assert Parameters.of({"a": 1}) != Parameters.of({"a": "1"})
    forward = Parameters.of({"a": 1, "b": "x", "c": True})
    backward = Parameters.of({"c": True, "b": "x", "a": 1})
    assert forward == backward
    assert hash(forward) == hash(backward)
    assert {forward: 1}[backward] == 1
    assert forward != {"a": 1, "b": "x", "c": True}
    assert forward != Payload.of({"a": 1, "b": "x", "c": True})


def test_parameters_are_immutable() -> None:
    source: dict[str, object] = {"a": 1}
    parameters = Parameters.of(source)
    source["a"] = 2
    source["b"] = 3
    assert dict(parameters) == {"a": 1}
    assert len(parameters) == 1
    mutable = cast(Any, parameters)
    with pytest.raises(TypeError):
        mutable["a"] = 2
    with pytest.raises(TypeError):
        del mutable["a"]
    with pytest.raises(AttributeError):
        mutable.a = 1
    with pytest.raises(AttributeError):
        mutable._payload = Payload.of({})
    with pytest.raises(AttributeError):
        del mutable._payload
    with pytest.raises(TypeError):
        cast(Any, Parameters)()
    assert not hasattr(parameters, "__dict__")
    assert parameters["a"] == 1


def test_parameters_copy_and_pickle_round_trip() -> None:
    parameters = Parameters.of({"n": 3, "p": Decimal("0.50"), "flag": True, "s": "x\u00e9"})
    for clone in (copy.copy(parameters), copy.deepcopy(parameters), pickle.loads(pickle.dumps(parameters))):
        assert type(clone) is Parameters
        assert clone == parameters
        assert hash(clone) == hash(parameters)
        assert str(clone["p"]) == "0.50"


def test_parameters_repr_shows_the_canonical_form() -> None:
    assert repr(Parameters.of({"a": 1})) == '<Parameters {"$map":{"a":1}}>'


def test_of_accepts_typed_dicts_and_pairs_under_strict_mypy() -> None:
    # `dict` is invariant: these typed variables must type-check as `Parameters.of` sources (covered by `make typecheck`).
    closes: dict[str, Decimal] = {"a": Decimal("1.0")}
    counts: dict[str, int] = {"a": 1, "b": 2}
    pairs: list[tuple[str, int]] = [("b", 2), ("a", 1)]
    assert Parameters.of(closes)["a"] == Decimal("1.0")
    assert Parameters.of(counts) == Parameters.of(pairs)
    lists: dict[str, list[int]] = {"a": [1, 2]}
    with pytest.raises(ValueError, match="'a'"):
        Parameters.of(lists)


def test_of_returns_an_exact_parameters_instance_unchanged() -> None:
    parameters = Parameters.of({"a": 1})
    assert Parameters.of(parameters) is parameters


def test_of_rejects_a_parameters_subclass_in_parameters_words() -> None:
    subclass = type("Sub", (Parameters,), {"__slots__": ()})
    instance: Any = object.__new__(subclass)
    with pytest.raises(PayloadError, match="a Parameters subclass"):
        Parameters.of(instance)
    with pytest.raises(PayloadError, match="payload source"):
        Payload.of(cast(Any, Parameters.of({"a": 1})))
