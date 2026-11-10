.PHONY: test lint format typecheck imports check

test:
	uv run pytest

lint:
	uv run ruff check src tests && uv run ruff format --check src tests

# Applies formatting and safe lint fixes.
format:
	uv run ruff check --fix src tests && uv run ruff format src tests

typecheck:
	uv run mypy

imports:
	uv run lint-imports

check: lint typecheck imports test
