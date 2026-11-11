"""Builders of Quasar `GET /v1/candles` responses for the decoder and client tests. Imports nothing from `tests.*`."""

import json
from collections.abc import Mapping, Sequence

from sentaris_engine.infrastructure.quasar.pages import PageRequest

FIVE_MINUTES = 300_000


def candle_json(
    open_time_ms: int,
    *,
    open: str = "82855.4",
    high: str = "82866.1",
    low: str = "82768.1",
    close: str = "82768.2",
    volume: str = "369.221",
    turnover: str | None = "30587379.8759",
    conflicted: bool = False,
) -> dict[str, object]:
    """One candle object as Quasar sends it."""
    return {
        "open_time_ms": open_time_ms,
        "open": open,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "turnover": turnover,
        "conflicted": conflicted,
    }


def page_json(
    request: PageRequest,
    candles: Sequence[dict[str, object]],
    *,
    oldest: int | None = None,
    newest: int | None = None,
    next_start: int | None = None,
) -> dict[str, object]:
    """A self-consistent page: echoes the request, coverage over `[start, next_start or end)`.

    `present_slots` counts the non-conflicted candles, `conflicted_slots` the flagged ones, `missing_slots` the rest;
    `gap_free` is true exactly when conflicted, unavailable, missing and beyond-stored are all 0.
    """
    if not candles and (oldest is None or newest is None):
        raise ValueError("oldest and newest are required when candles is empty")
    if oldest is None:
        oldest = int(str(candles[0]["open_time_ms"]))
    if newest is None:
        newest = int(str(candles[-1]["open_time_ms"]))
    span_end = request.end if next_start is None else next_start
    slots = (span_end - request.start) // request.timeframe_ms
    conflicted = sum(1 for candle in candles if candle["conflicted"] is True)
    present = len(candles) - conflicted
    missing = slots - present - conflicted
    return {
        "venue": request.venue,
        "symbol": request.symbol,
        "timeframe": request.timeframe,
        "start": request.start,
        "end": request.end,
        "series": {"oldest_open_time_ms": oldest, "newest_open_time_ms": newest},
        "candles": list(candles),
        "next": next_start,
        "coverage": {
            "span": {"start": request.start, "end": span_end},
            "slots": slots,
            "present_slots": present,
            "conflicted_slots": conflicted,
            "unavailable_slots": 0,
            "missing_slots": missing,
            "beyond_stored_slots": 0,
            "gap_free": conflicted == 0 and missing == 0,
        },
    }


def error_body(code: str, message: str = "m", details: Mapping[str, object] | None = None) -> bytes:
    """A contract section 2 error body."""
    return encode({"error": {"code": code, "message": message, "details": dict(details or {})}})


def encode(value: object) -> bytes:
    """`value` as UTF-8 JSON."""
    return json.dumps(value).encode("utf-8")


EXAMPLE_REQUEST = PageRequest(
    venue="binance-usdm",
    symbol="BTC/USDT:USDT",
    timeframe="5m",
    timeframe_ms=FIVE_MINUTES,
    start=1792643400000,
    end=1792673400000,
    limit=3,
)

# Contract section 5.2, verbatim.
EXAMPLE_BODY: bytes = b"""{
  "venue": "binance-usdm",
  "symbol": "BTC/USDT:USDT",
  "timeframe": "5m",
  "start": 1792643400000,
  "end": 1792673400000,
  "series": {
    "oldest_open_time_ms": 1792643400000,
    "newest_open_time_ms": 1792673100000
  },
  "candles": [
    {
      "open_time_ms": 1792643400000,
      "open": "82855.4",
      "high": "82866.1",
      "low": "82768.1",
      "close": "82768.2",
      "volume": "369.221",
      "turnover": "30587379.8759",
      "conflicted": false
    },
    {
      "open_time_ms": 1792643700000,
      "open": "82768.2",
      "high": "82768.2",
      "low": "82664.7",
      "close": "82709",
      "volume": "580.95",
      "turnover": "48054366.2802",
      "conflicted": false
    },
    {
      "open_time_ms": 1792644000000,
      "open": "82709.1",
      "high": "82765.3",
      "low": "82686.2",
      "close": "82744.5",
      "volume": "380.864",
      "turnover": "31506256.9708",
      "conflicted": false
    }
  ],
  "next": 1792644300000,
  "coverage": {
    "span": { "start": 1792643400000, "end": 1792644300000 },
    "slots": 3,
    "present_slots": 3,
    "conflicted_slots": 0,
    "unavailable_slots": 0,
    "missing_slots": 0,
    "beyond_stored_slots": 0,
    "gap_free": true
  }
}
"""
