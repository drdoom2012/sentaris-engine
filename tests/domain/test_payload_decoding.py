import sys
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest

from sentaris_engine.domain.payload import Payload, PayloadError
from tests.support.vectors import CORPUS, VECTORS

_FORMS = [(name, expected) for name, _, expected in VECTORS] + [
    (f"corpus-{name}", Payload.of(build()).canonical()) for name, build in CORPUS
]


def shape(value: object) -> object:
    """The value with every kind made explicit: `bool` is not `int`, `Decimal` keeps its exponent."""
    if type(value) is Payload:
        return ("Payload", tuple((key, shape(item)) for key, item in value.items()))
    if type(value) is tuple:
        return ("tuple", tuple(shape(item) for item in value))
    if type(value) is Decimal:
        return ("Decimal", str(value), value.as_tuple())
    return (type(value).__name__, value, None)


@pytest.mark.parametrize("data", [form for _, form in _FORMS], ids=[name for name, _ in _FORMS])
def test_round_trip_bytes(data: bytes) -> None:
    assert Payload.from_canonical(data).canonical() == data


@pytest.mark.parametrize("build", [build for _, build in CORPUS], ids=[name for name, _ in CORPUS])
def test_round_trip_value_keeps_every_kind(build: Callable[[], Any]) -> None:
    payload = Payload.of(build())
    decoded = Payload.from_canonical(payload.canonical())
    assert decoded == payload
    assert shape(decoded) == shape(payload)


def test_shape_tells_apart_what_python_equality_does_not() -> None:
    assert shape(Payload.of({"v": True})) != shape(Payload.of({"v": 1}))
    assert shape(Payload.of({"v": Decimal("1.0")})) != shape(Payload.of({"v": Decimal("1.00")}))
    assert shape(Payload.of({"v": Decimal(1)})) != shape(Payload.of({"v": "1"}))
    assert shape(Payload.of({"v": None})) != shape(Payload.of({}))
    assert shape(Payload.of({"v": [1, 2]})) != shape(Payload.of({"v": [2, 1]}))


# Each case changes exactly one thing in a canonical form that `test_round_trip_bytes` accepts. Backslashes in
# escape sequences are doubled, so the bytes hold a backslash followed by the escape letters.
_NON_CANONICAL: list[tuple[str, bytes]] = [
    ("leading-space", b' {"$map":{}}'),
    ("trailing-space", b'{"$map":{}} '),
    ("trailing-newline", b'{"$map":{}}\n'),
    ("bom-prefix", b'\xef\xbb\xbf{"$map":{}}'),
    ("space-after-colon", b'{"$map":{"a": true}}'),
    ("unsorted-keys", b'{"$map":{"b":1,"a":true}}'),
    ("duplicate-keys", b'{"$map":{"a":true,"a":true}}'),
    ("escape-uppercase-hex", b'{"$map":{"k":"\\u001B"}}'),
    ("escape-printable", b'{"$map":{"k":"\\u0041"}}'),
    ("escape-solidus", b'{"$map":{"k":"\\/"}}'),
    ("escaped-surrogate-pair", b'{"$map":{"k":"\\ud83d\\ude00"}}'),
    ("escaped-lone-surrogate", b'{"$map":{"k":"\\ud800"}}'),
    ("decimal-as-json-number", b'{"$map":{"d":1.5}}'),
    ("decimal-unnormalized-exponent", b'{"$map":{"d":{"$decimal":"1.0E+1"}}}'),
    ("decimal-lowercase-e", b'{"$map":{"d":{"$decimal":"1e+1"}}}'),
    ("decimal-leading-zero", b'{"$map":{"d":{"$decimal":"01"}}}'),
    ("decimal-plus-sign", b'{"$map":{"d":{"$decimal":"+1"}}}'),
    ("decimal-underscore", b'{"$map":{"d":{"$decimal":"1_0"}}}'),
    ("decimal-leading-space", b'{"$map":{"d":{"$decimal":" 1"}}}'),
    ("decimal-not-a-number-text", b'{"$map":{"d":{"$decimal":"abc"}}}'),
    ("decimal-nan", b'{"$map":{"d":{"$decimal":"NaN"}}}'),
    ("decimal-exponent-overflow", b'{"$map":{"d":{"$decimal":"1E+999999999999999999999"}}}'),
    ("int-leading-zero", b'{"$map":{"n":01}}'),
    ("int-negative-zero", b'{"$map":{"n":-0}}'),
    ("int-above-range", b'{"$map":{"n":9007199254740992}}'),
    ("int-below-range", b'{"$map":{"n":-9007199254740992}}'),
    ("int-17-digits", b'{"$map":{"n":10000000000000000}}'),
    ("int-arabic-indic-digit", b'{"$map":{"n":\xd9\xa1}}'),
    ("int-superscript-two", b'{"$map":{"n":\xc2\xb2}}'),
    ("invalid-utf-8", b'{"$map":{"k":"\xff"}}'),
    ("tag-unknown-key", b'{"$map":{"a":{"$other":"1"}}}'),
    ("tag-extra-key", b'{"$map":{"a":{"$decimal":"1","x":1}}}'),
    ("top-null", b"null"),
    ("top-sequence", b"[]"),
    ("top-decimal", b'{"$decimal":"1"}'),
    ("empty", b""),
    ("truncated", b'{"$map":{"a":true}'),
    ("value-nan", b'{"$map":{"n":NaN}}'),
    ("value-infinity", b'{"$map":{"n":Infinity}}'),
    ("value-exponent", b'{"$map":{"n":1e5}}'),
    ("top-nan", b"NaN"),
    ("top-infinity", b"Infinity"),
    ("top-fraction", b"1.5"),
    ("top-exponent", b"1e5"),
]


@pytest.mark.parametrize("data", [data for _, data in _NON_CANONICAL], ids=[name for name, _ in _NON_CANONICAL])
def test_decoder_rejects_non_canonical_input(data: bytes) -> None:
    with pytest.raises(PayloadError):
        Payload.from_canonical(data)


def test_deep_nesting_decodes_beyond_recursion_limit() -> None:
    depth = 5 * sys.getrecursionlimit()
    value: Any = None
    for level in range(depth):
        value = [value] if level % 2 else {"n": value}
    form = Payload.of({"root": value}).canonical()
    decoded = Payload.from_canonical(form)
    assert decoded.canonical() == form
    assert form.count(b"[") == depth // 2
