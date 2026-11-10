import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from sentaris_engine.domain.payload import Payload
from tests.support.vectors import CORPUS, VECTORS

_SCRIPT = Path(__file__).resolve().parents[1] / "support" / "encode_corpus.py"
_ENTRIES: list[tuple[str, Callable[[], Any]]] = [(name, build) for name, build, _ in VECTORS] + list(CORPUS)


def _run_child(args: list[str], seed: str) -> list[str]:
    # `-P` keeps the working directory off `sys.path`; `-I` is not used because it would ignore PYTHONHASHSEED.
    result = subprocess.run(
        [sys.executable, "-P", *args],
        env={"PYTHONHASHSEED": seed},
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"child {args} exited with {result.returncode}: {result.stderr}"
    return result.stdout.splitlines()


@pytest.mark.parametrize(("seed", "profile"), [("0", "default"), ("1", "odd"), ("4242", "odd")])
def test_encoding_is_identical_across_processes(seed: str, profile: str) -> None:
    expected_here = {name: Payload.of(build()).canonical() for name, build in _ENTRIES}
    expected_vectors = {name: expected for name, _, expected in VECTORS}

    lines = _run_child([str(_SCRIPT), profile], seed)

    assert len(lines) == 2 * len(_ENTRIES)
    for (name, _), first, second in zip(_ENTRIES, lines[0::2], lines[1::2], strict=True):
        assert first == f"{name} {expected_here[name].hex()}"
        assert second == f"{name}.again {expected_here[name].hex()}"
        if name in expected_vectors:
            assert first == f"{name} {expected_vectors[name].hex()}"


def test_child_process_honours_the_hash_seed() -> None:
    def child_hash(seed: str) -> str:
        return "".join(_run_child(["-c", "print(hash('a'))"], seed))

    assert child_hash("1") != child_hash("2")
    assert child_hash("1") == child_hash("1")
