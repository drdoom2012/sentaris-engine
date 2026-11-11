"""Reading stored candles from the Quasar Market Data REST API over HTTP (DR-18).

Scope: `GET /v1/candles` only. What is returned are stored rows as Quasar states them; no snapshot, availability,
freshness or completeness is claimed (DR-06, DR-21, OD-6, OD-7).
"""

from sentaris_engine.infrastructure.quasar.client import MAX_PAGE_LIMIT, MAX_WINDOW_SLOTS, TIMEFRAME_MS, QuasarClient
from sentaris_engine.infrastructure.quasar.pages import CandlePage, CandleRead

__all__ = ["MAX_PAGE_LIMIT", "MAX_WINDOW_SLOTS", "TIMEFRAME_MS", "CandlePage", "CandleRead", "QuasarClient"]
