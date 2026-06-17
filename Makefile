.PHONY: help install lint format typecheck test clean

help:  ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install:  ## Install all dependencies (including dev)
	uv sync

lint:  ## Run ruff linter
	uv run ruff check src tests

format:  ## Run ruff formatter
	uv run ruff format src tests

typecheck:  ## Run pyright and mypy type checkers
	uv run pyright src
	uv run mypy src

test:  ## Run unit tests with coverage
	uv run pytest tests/unit

clean:  ## Remove build artifacts and cache files
	rm -rf htmlcov .coverage dist build .mypy_cache .ruff_cache __pycache__
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
