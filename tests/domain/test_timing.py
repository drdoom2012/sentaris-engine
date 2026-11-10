from decimal import Decimal
from typing import Any, cast

import pytest

from sentaris_engine.domain.timing import require_duration, require_instant


def test_instant_accepts_int() -> None:
    assert require_instant(1_700_000_000_000, "as_of") == 1_700_000_000_000
    assert require_instant(0, "as_of") == 0
    assert require_instant(-1, "as_of") == -1


@pytest.mark.parametrize("value", [True, False, 1.0, "1", Decimal(1), None, b"1", [1]], ids=repr)
def test_instant_rejects_non_int(value: object) -> None:
    with pytest.raises(ValueError, match="as_of"):
        require_instant(cast(Any, value), "as_of")


def test_instant_rejects_int_subclass() -> None:
    class Millis(int):
        pass

    with pytest.raises(ValueError, match="as_of"):
        require_instant(Millis(1), "as_of")


def test_duration_accepts_positive_int() -> None:
    assert require_duration(60_000, "timeframe_ms") == 60_000
    assert require_duration(1, "timeframe_ms") == 1


@pytest.mark.parametrize("value", [0, -1, -60_000, True, False, 1.0, "1", Decimal(1), None], ids=repr)
def test_duration_rejects_zero_negative_and_bool(value: object) -> None:
    with pytest.raises(ValueError, match="timeframe_ms"):
        require_duration(cast(Any, value), "timeframe_ms")
