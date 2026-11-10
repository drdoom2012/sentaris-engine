"""Child process for the cross-process stability test: print the canonical bytes of every vector and corpus entry.

Usage: `python -P encode_corpus.py default|odd`. For each entry `<id>` it prints `<id> <hex>` (the canonical bytes of
the payload built from the entry) and `<id>.again <hex>` (the canonical bytes of the payload decoded from them).
`odd` runs under a `decimal` context that differs from the default in every setting that could leak into the text.
"""

import importlib.util
import sys
from decimal import (
    ROUND_DOWN,
    Clamped,
    Context,
    DivisionByZero,
    FloatOperation,
    Inexact,
    InvalidOperation,
    Overflow,
    Rounded,
    Subnormal,
    Underflow,
    setcontext,
)
from pathlib import Path
from typing import Any

from sentaris_engine.domain.payload import Payload

_ALL_TRAPS = [
    Clamped,
    DivisionByZero,
    FloatOperation,
    Inexact,
    InvalidOperation,
    Overflow,
    Rounded,
    Subnormal,
    Underflow,
]


def _load_vectors() -> Any:
    # Loaded by absolute path: the child cannot import `tests`. Registered before `exec_module` because dataclasses
    # with string annotations look their module up in `sys.modules`.
    path = Path(__file__).resolve().parent / "vectors.py"
    spec = importlib.util.spec_from_file_location("payload_vectors", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main(profile: str) -> None:
    vectors = _load_vectors()
    if profile == "odd":
        setcontext(Context(capitals=0, prec=3, rounding=ROUND_DOWN, traps=_ALL_TRAPS))
    elif profile != "default":
        raise SystemExit(f"unknown profile {profile!r}")
    entries = [(name, build) for name, build, _ in vectors.VECTORS] + list(vectors.CORPUS)
    for name, build in entries:
        canonical = Payload.of(build()).canonical()
        again = Payload.from_canonical(canonical).canonical()
        print(f"{name} {canonical.hex()}")
        print(f"{name}.again {again.hex()}")


if __name__ == "__main__":
    main(sys.argv[1])
