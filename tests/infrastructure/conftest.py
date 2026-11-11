from collections.abc import Iterator

import pytest

from tests.support.quasar_stub import StubQuasar

_PROXY_VARIABLES = ("http_proxy", "https_proxy", "all_proxy", "no_proxy")


@pytest.fixture(autouse=True)
def hermetic_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    """No developer proxy reaches the stub on 127.0.0.1; a test that exercises a proxy sets its own variables."""
    for name in _PROXY_VARIABLES:
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.upper(), raising=False)
    # Must stay: with NO_PROXY set, urllib's getproxies() is non-empty, so the macOS system-configuration proxy is never
    # consulted, and proxy_bypass honours "*".
    monkeypatch.setenv("NO_PROXY", "*")


@pytest.fixture
def stub() -> Iterator[StubQuasar]:
    with StubQuasar() as running:
        yield running
