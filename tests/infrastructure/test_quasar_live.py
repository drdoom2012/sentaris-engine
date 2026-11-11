"""Tests against a running Quasar API, excluded by default (`pytest -m live`).

Real values are read only through the client and no stored value is asserted. `QUASAR_BASE_URL` is required;
`QUASAR_LIVE_SYMBOL` names a series the deployment stores (default: the contract's example, which may not be stored).
"""

import os
from decimal import Decimal

import pytest

from sentaris_engine.infrastructure.quasar.client import QuasarClient
from sentaris_engine.infrastructure.quasar.errors import UnknownSeriesError
from sentaris_engine.infrastructure.quasar.pages import CandlePage

VENUE = "binance-usdm"
TIMEFRAME = "5m"
FIVE_MINUTES = 300_000
EARLIEST_SLOT = 946684800000
MAX_END = 4102444800000 + FIVE_MINUTES
DEFAULT_SYMBOL = "BTC/USDT:USDT"

pytestmark = pytest.mark.live


@pytest.fixture
def client() -> QuasarClient:
    base_url = os.environ.get("QUASAR_BASE_URL")
    if not base_url:
        pytest.skip("QUASAR_BASE_URL is not set; the live tests need a running Quasar API")
    return QuasarClient(base_url)


@pytest.fixture
def symbol() -> str:
    return os.environ.get("QUASAR_LIVE_SYMBOL", DEFAULT_SYMBOL)


def earliest_page(client: QuasarClient, symbol: str) -> CandlePage:
    """The earliest valid slot of the series; skips when the deployment does not store the symbol."""
    try:
        return client.fetch_page(VENUE, symbol, TIMEFRAME, EARLIEST_SLOT, EARLIEST_SLOT + FIVE_MINUTES)
    except UnknownSeriesError:
        pytest.skip(f"the deployment does not store {symbol!r} on {VENUE}; set QUASAR_LIVE_SYMBOL to a stored symbol")


def test_unknown_series_is_a_typed_error(client: QuasarClient) -> None:
    with pytest.raises(UnknownSeriesError):
        client.fetch_page(VENUE, "SENTARIS-NO-SUCH-SERIES", TIMEFRAME, EARLIEST_SLOT, EARLIEST_SLOT + FIVE_MINUTES)


def test_reads_exact_decimals_from_a_populated_series(client: QuasarClient, symbol: str) -> None:
    page = earliest_page(client, symbol)
    oldest, newest = page.oldest_open_time_ms, page.newest_open_time_ms
    result = client.read_candles(
        VENUE, symbol, TIMEFRAME, oldest, min(oldest + 10 * FIVE_MINUTES, newest + FIVE_MINUTES)
    )
    assert len(result.candles) >= 1
    for page in result.pages:
        assert page.coverage.span_start == page.start
        assert page.coverage.slots >= len(page.candles)
    for candle in result.candles:
        for value in (candle.open, candle.high, candle.low, candle.close, candle.volume):
            assert type(value) is Decimal
        assert candle.turnover is None or type(candle.turnover) is Decimal
        assert type(candle.conflicted) is bool
    times = [candle.open_time_ms for candle in result.candles]
    assert times == sorted(set(times))


def test_a_window_after_the_newest_candle_is_an_empty_page_not_an_error(client: QuasarClient, symbol: str) -> None:
    newest = earliest_page(client, symbol).newest_open_time_ms
    start, end = newest + FIVE_MINUTES, newest + 2 * FIVE_MINUTES
    if end > MAX_END:
        pytest.skip(f"the newest candle is too close to Quasar's end bound ({MAX_END}) for a window after it")
    assert client.fetch_page(VENUE, symbol, TIMEFRAME, start, end).candles == ()
