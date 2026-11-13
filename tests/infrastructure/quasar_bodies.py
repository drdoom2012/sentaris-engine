"""The Quasar response bodies of `fixtures/`, the request each `200` body answers, and one-edit helpers (spec 8)."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, final

from sentaris_engine.infrastructure.quasar import CandlePage, FundingRatePage, HttpResponse, OpenInterestPage
from sentaris_engine.infrastructure.quasar.decoding import (
    decode_candle_page,
    decode_funding_rate_page,
    decode_open_interest_page,
)

FIXTURES: Final = Path(__file__).parent / "fixtures"
JSON_UTF8: Final = "application/json; charset=utf-8"

# Body name -> the contract section (`../quasar-market-data/docs/contracts/api-v1.md`) it follows.
BODIES: Final[dict[str, str]] = {
    "candles_example": "contract 5.2 (verbatim)",
    "open_interest_example": "contract 6.5.4 (verbatim)",
    "funding_example": "contract 6.7.4 (verbatim)",
    "candles_paged_1": "contract 3, 5.2, 5.3",
    "candles_paged_2": "contract 3, 5.2, 5.3",
    "candles_paged_3": "contract 3, 5.2, 5.3",
    "candles_empty": "contract 5.1, 5.2 (existing series, nothing in the window)",
    "open_interest_paged_1": "contract 3, 6.5.4",
    "open_interest_paged_2": "contract 3, 6.5.4",
    "funding_paged_1": "contract 6.7.3, 6.7.4",
    "funding_paged_2": "contract 6.7.3, 6.7.4",
    "funding_series_null": "contract 6.7.4 (series null, decision FA4)",
    "error_400_invalid_parameter": "contract 2 (verbatim example)",
    "error_404_unknown_series": "contract 2",
    "error_404_not_found": "contract 2",
    "error_405_method_not_allowed": "contract 2",
    "error_500_internal_error": "contract 2",
    "error_503_not_ready": "contract 2",
}

type Endpoint = Literal["candles", "open_interest", "funding"]


@final
@dataclass(frozen=True, slots=True)
class Request:
    """The request a `200` body answers; `series` is the timeframe or period (`None` for funding), and for
    funding `end` is `end_inclusive`."""

    endpoint: Endpoint
    venue: str
    symbol: str
    series: str | None
    start: int
    end: int
    limit: int | None


_BTC: Final = ("binance-usdm", "BTC/USDT:USDT")

REQUESTS: Final[dict[str, Request]] = {
    "candles_example": Request("candles", *_BTC, "5m", 1792643400000, 1792673400000, 3),
    "open_interest_example": Request("open_interest", *_BTC, "5m", 1792672500000, 1792674600000, None),
    "funding_example": Request("funding", *_BTC, None, 1792656000000, 1792720000000, None),
    "candles_paged_1": Request("candles", *_BTC, "5m", 1792643400000, 1792646400000, 2),
    "candles_paged_2": Request("candles", *_BTC, "5m", 1792644300000, 1792646400000, 2),
    "candles_paged_3": Request("candles", *_BTC, "5m", 1792644900000, 1792646400000, 2),
    "candles_empty": Request("candles", *_BTC, "5m", 1792673400000, 1792673700000, None),
    "open_interest_paged_1": Request("open_interest", *_BTC, "5m", 1792672500000, 1792674600000, 2),
    "open_interest_paged_2": Request("open_interest", *_BTC, "5m", 1792673400000, 1792674600000, 2),
    "funding_paged_1": Request("funding", *_BTC, None, 1792656000000, 1792720000000, 3),
    "funding_paged_2": Request("funding", *_BTC, None, 1792713600000, 1792720000000, 3),
    "funding_series_null": Request(
        "funding", "binance-usdm", "ETH/USDT:USDT", None, 1792656000000, 1792720000000, None
    ),
}

type Page = CandlePage | OpenInterestPage | FundingRatePage


def load(name: str) -> bytes:
    """The bytes of the fixture `name`."""
    return (FIXTURES / f"{name}.json").read_bytes()


def decode_as(request: Request, body: bytes) -> Page:
    """Run the decoder of `request.endpoint` on a `200` response with `body`."""
    response = HttpResponse(200, JSON_UTF8, body)
    if request.endpoint == "funding":
        return decode_funding_rate_page(
            response, request.venue, request.symbol, request.start, request.end, request.limit
        )
    if request.series is None:
        raise ValueError("a candle or open interest request needs a timeframe or period")
    if request.endpoint == "candles":
        return decode_candle_page(
            response, request.venue, request.symbol, request.series, request.start, request.end, request.limit
        )
    return decode_open_interest_page(
        response, request.venue, request.symbol, request.series, request.start, request.end, request.limit
    )


def decode(name: str, body: bytes | None = None) -> Page:
    """Run the decoder matching `name` with `REQUESTS[name]` on `body` (default: the fixture itself)."""
    return decode_as(REQUESTS[name], load(name) if body is None else body)


@final
class Raw:
    """JSON text spliced into an edited body verbatim (for values `json.dumps` cannot write, such as `1.5`)."""

    def __init__(self, text: str) -> None:
        self.text = text


@final
class _Delete:
    def __repr__(self) -> str:
        return "DELETE"


DELETE: Final = _Delete()


def _placeholders(value: object, raws: list[str]) -> object:
    """`value` with every `Raw` replaced by a unique placeholder string, recorded in `raws`."""
    if type(value) is Raw:
        raws.append(value.text)
        return f"\x00raw{len(raws) - 1}\x00"
    if type(value) is dict:
        return {key: _placeholders(item, raws) for key, item in value.items()}
    if type(value) is list:
        return [_placeholders(item, raws) for item in value]
    return value


def edited(name: str, path: tuple[str | int, ...], value: object) -> bytes:
    """The fixture `name` with the value at `path` replaced or added (`DELETE` removes the key)."""
    tree = json.loads(load(name))
    parent = tree
    for step in path[:-1]:
        parent = parent[step]
    raws: list[str] = []
    if value is DELETE:
        del parent[path[-1]]
    else:
        parent[path[-1]] = _placeholders(value, raws)
    text = json.dumps(tree, ensure_ascii=False)
    for index, raw in enumerate(raws):
        text = text.replace(json.dumps(f"\x00raw{index}\x00", ensure_ascii=False), raw)
    return text.encode()
