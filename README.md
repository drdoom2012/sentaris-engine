# Sentaris Engine

Independent application for deterministic analysis of cryptocurrency market data. Market data comes exclusively from
the [Quasar Market Data](../quasar-market-data) REST API. No strategy is implemented yet; this is the project foundation.

## Development

Requires [uv](https://docs.astral.sh/uv/) (it installs Python 3.12 from `.python-version`).

```sh
uv sync          # create .venv and install dev dependencies
make check       # lint, typecheck, imports, test (what CI runs)
make format      # apply ruff formatting and safe fixes
```

Individual checks: `make lint`, `make typecheck`, `make imports`, `make test`.
One test: `uv run pytest tests/test_package.py::test_version_is_semver`.

## Documentation

`docs/domain.md` is the single source of truth for what the engine analyses, its business rules and the open decisions. `CLAUDE.md` holds the working instructions for Claude Code.
