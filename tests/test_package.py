import importlib

import pytest


@pytest.mark.parametrize(
    "name",
    [
        "sentaris_engine",
        "sentaris_engine.domain",
        "sentaris_engine.application",
        "sentaris_engine.strategies",
        "sentaris_engine.infrastructure",
    ],
)
def test_package_imports(name: str) -> None:
    assert importlib.import_module(name).__doc__
