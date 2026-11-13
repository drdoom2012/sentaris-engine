"""Quasar Market Data REST client (SE-6; R1). Reaches Quasar only through its REST API (DR-18, DR-19)."""

from sentaris_engine.infrastructure.quasar.client import QuasarClient
from sentaris_engine.infrastructure.quasar.errors import (
    QuasarClientError,
    QuasarProtocolError,
    QuasarResponseError,
    QuasarTransportError,
)
from sentaris_engine.infrastructure.quasar.pages import CandlePage, FundingRatePage, OpenInterestPage, SeriesBounds
from sentaris_engine.infrastructure.quasar.transport import HttpResponse, Transport, urllib_transport

__all__ = [
    "CandlePage",
    "FundingRatePage",
    "HttpResponse",
    "OpenInterestPage",
    "QuasarClient",
    "QuasarClientError",
    "QuasarProtocolError",
    "QuasarResponseError",
    "QuasarTransportError",
    "SeriesBounds",
    "Transport",
    "urllib_transport",
]
