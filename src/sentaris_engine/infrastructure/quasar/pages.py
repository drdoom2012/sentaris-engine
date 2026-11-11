"""The values of one decoded `GET /v1/candles` page and of a read made of several pages (contract sections 3, 5).

Only the decoder builds a `PageCoverage` or a `CandlePage`, and it has checked them by then; these types carry no
checks of their own. They carry what Quasar stated, nothing more: `conflicted` and `coverage` are not interpreted
(OD-7), and no availability or completeness is established (DR-06, DR-21, OD-6).
"""

from __future__ import annotations

from dataclasses import dataclass

from sentaris_engine.domain.market import Candle
from sentaris_engine.domain.timing import EpochMs


@dataclass(frozen=True, slots=True)
class PageRequest:
    """What one page request asked for: the series, its timeframe in milliseconds, the window and the page size."""

    venue: str
    symbol: str
    timeframe: str
    timeframe_ms: int
    start: EpochMs
    end: EpochMs
    limit: int


@dataclass(frozen=True, slots=True)
class PageCoverage:
    """The `coverage` block of a page as Quasar stated it (contract section 5.3).

    It speaks for this page's span only.
    """

    span_start: EpochMs
    span_end: EpochMs
    slots: int
    present_slots: int
    conflicted_slots: int
    unavailable_slots: int
    missing_slots: int
    beyond_stored_slots: int
    gap_free: bool


@dataclass(frozen=True, slots=True)
class CandlePage:
    """One page of stored candles, ascending, with the cursor to the next page and the page's own coverage."""

    start: EpochMs
    end: EpochMs
    oldest_open_time_ms: EpochMs
    newest_open_time_ms: EpochMs
    candles: tuple[Candle, ...]
    next_start: EpochMs | None
    coverage: PageCoverage


@dataclass(frozen=True, slots=True)
class CandleRead:
    """The pages read for one window, in order.

    The pages are separate reads taken at separate moments and are NOT one snapshot (contract section 3, OD-24):
    nothing here detects a change between them. No availability and no completeness is established (DR-06, DR-21,
    OD-6); `conflicted` and `coverage` are carried as Quasar stated them (OD-7).
    """

    start: EpochMs
    end: EpochMs
    pages: tuple[CandlePage, ...]

    @property
    def candles(self) -> tuple[Candle, ...]:
        """The candles of all pages, in page order."""
        return tuple(candle for page in self.pages for candle in page.candles)
