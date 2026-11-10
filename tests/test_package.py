import importlib
import re

import pytest

import sentaris_engine

LAYERS = ["domain", "strategies", "infrastructure", "application"]


def test_version_is_semver() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", sentaris_engine.__version__)


@pytest.mark.parametrize("layer", LAYERS)
def test_layer_package_is_importable(layer: str) -> None:
    assert importlib.import_module(f"sentaris_engine.{layer}").__doc__
