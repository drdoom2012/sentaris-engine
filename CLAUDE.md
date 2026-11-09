# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Sentaris Engine is an independent application for deterministic analysis of cryptocurrency market data from the Quasar Market Data REST API (sibling project `../quasar-market-data`). What it analyses and the rules it obeys are in `docs/domain.md`.

Current state: project foundation only. No strategy, signal, backtest, persistence or REST endpoint exists yet; do not add them without an explicit request (`docs/domain.md`, section 2).

Stack: Python 3.12, uv, `src/` layout (package `sentaris_engine`), pytest, ruff, mypy (strict), import-linter. There are no runtime dependencies; adding one needs a concrete reason.

## Commands

- `uv sync` — create `.venv` and install dev dependencies.
- `make check` — lint, typecheck, imports, test; exactly what CI runs. Must pass before work is reported done.
- `make lint` / `make typecheck` / `make imports` / `make test` — individual checks (`ruff check` + `ruff format --check`, `mypy`, `lint-imports`, `pytest`).
- `make format` — apply ruff formatting and safe fixes.
- One test: `uv run pytest tests/test_package.py::test_version_is_semver`.

CI (`.github/workflows/check.yml`) runs with `UV_LOCKED=1`: commit `uv.lock` whenever dependencies change. Action versions are pinned by commit SHA.

## Architecture

Dependency direction, enforced by the `layers` contract in `pyproject.toml`:

```
application  →  strategies | infrastructure  →  domain
```

Upper layers may import lower ones, never the reverse. `strategies` and `infrastructure` are siblings and must not import each other.

- **domain** — pure types and rules for market data and signals.
- **strategies** — pure evaluation of an evaluation context (`docs/domain.md`, section 3). Never fetches data, never knows whether it runs live or in replay.
- **infrastructure** — all I/O: the Quasar REST API client, the real clock. Implements what upper layers need.
- **application** — orchestration: builds snapshots from data sources, calls strategies, for live scanning and historical replay. The only layer that combines strategies with infrastructure. It reaches I/O only through infrastructure; this is a convention, not yet mechanically enforced (revisit when it has code).

### Pure logic vs I/O is enforced by contract

`domain` and `strategies` are **default-deny**: the `forbidden` contract "domain and strategies import only allowlisted pure standard-library modules" rejects every import, third-party or standard library, that is not in its `ignore_imports` allowlist (`dataclasses`, `decimal`, `enum`, `datetime`, `typing`, …). A new import there fails `make imports` until it is deliberately allowlisted; allowlist only modules that cannot do I/O, read the clock or generate randomness. Do not "fix" a failure by moving the import into a pure layer's dependency chain: the contract also catches indirect imports. Needing I/O or a third-party library means the code belongs in `infrastructure` behind a type the pure layers own.

`ruff` bans wall-clock reads (`datetime.now/utcnow/today`, `date.today`; TID251) everywhere except `infrastructure/`. A third contract forbids importing `quasar_market_data`. When adding a layer, change the contracts in the same commit.

## Domain Rules

`docs/domain.md` is the single source of truth for business rules: strategy independence, availability and look-ahead bias, determinism, data quality, data inputs and the open decisions (`OD-xx`). Read it before touching a strategy, snapshot, data input or result type.

- Do not restate its rules here or elsewhere; cite the ID (`DR-xx`, `OD-xx`).
- Do not decide an open decision by implementing it; ask.
- A change in behavior, a new data input or a new check updates `docs/domain.md` in the same commit.

## Engineering Conventions

(Aligned with Quasar Market Data.)

- Prefer simple solutions over speculative abstractions; no frameworks or dependencies without need. Keep changes small; no unrelated refactoring.
- Quasar boundary and trading exclusions: DR-18, DR-19.
- Handle errors explicitly; avoid global mutable state.
- ruff line length 120; lint rules are defaults plus `I`, `UP`, `B`, `DTZ`, `TID251`. mypy is strict over `src` and `tests`; annotate everything.
- Tests use pytest. Anything needing a running Quasar API is marked `live` and excluded by default; register new markers in `pyproject.toml` (`--strict-markers`).
- Never weaken a check, contract or test to make it pass. Never claim a check passed unless it actually ran.

## References

- `docs/domain.md` — domain, business rules, open decisions (single source of truth)
- `../quasar-market-data/docs/contracts/api-v1.md` — the data contract; check it before relying on any field's semantics
- Superpowers specs and plans: `docs/superpowers/specs/` and `docs/superpowers/plans/`; they link to `docs/domain.md` IDs and do not copy rule text

If a referenced document does not exist, report it before proceeding.
