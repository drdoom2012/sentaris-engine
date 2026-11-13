"""Shared helpers of the SE-3 tests: the exact-exception assertion and the N15 list of unexpected values."""

from collections.abc import Callable, Iterator
from decimal import Decimal
from enum import Enum

import pytest


def raises_exactly(exc_type: type[BaseException], fn: Callable[[], object]) -> None:
    """Call `fn` and assert that it raised an exception whose type is exactly `exc_type` (no subclass check)."""
    with pytest.raises(BaseException) as info:
        fn()
    assert type(info.value) is exc_type, f"expected exactly {exc_type.__name__}, got {type(info.value).__name__}"


class _IntSub(int):
    pass


class _StrSub(str):
    pass


class _DecimalSub(Decimal):
    pass


class _Plain(Enum):
    A = "a"


def _generator() -> Iterator[int]:
    yield 1


UNEXPECTED_VALUES: tuple[object, ...] = (
    None,
    object(),
    1.0,
    b"x",
    {1},
    _generator(),
    "1",
    1,
    _IntSub(1),
    _StrSub("1"),
    _DecimalSub("1"),
    _Plain.A,
)

UNEXPECTED_IDS: tuple[str, ...] = (
    "None",
    "object",
    "float",
    "bytes",
    "set",
    "generator",
    "str-number",
    "int",
    "int-subclass",
    "str-subclass",
    "Decimal-subclass",
    "Enum-member",
)
