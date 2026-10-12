.PHONY: help install api-docs fmt lint lint-md types test coverage check build spec-sync

help: ## Show this help
	@grep -hE '^[a-z-]+:.*?##' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  %-12s %s\n", $$1, $$2}'

install: ## Create the environment and install the project
	uv sync --extra dev

api-docs: ## Regenerate the README's API reference from the code
	uv run python tools/api_reference.py --write

fmt: ## Format the source
	uv run ruff format src tests
	uv run ruff check --fix src tests

lint: ## Lint, and check formatting without changing anything
	uv run ruff check src tests
	uv run ruff format --check src tests

lint-md: ## Lint the Markdown
	@if command -v markdownlint >/dev/null 2>&1; then \
		markdownlint '**/*.md'; \
	elif command -v npx >/dev/null 2>&1; then \
		npx --yes markdownlint-cli '**/*.md'; \
	else \
		echo "lint-md: no markdownlint and no npx; skipped"; exit 1; \
	fi
	@echo "lint-md: markdown is clean"

types: ## Type-check with mypy and with the editor's language server
	uv run mypy
	uv run basedpyright src tests

test: ## Run the tests
	uv run pytest

# coverage run starts measuring before Python imports anything, so the
# plugin, which pytest imports while it registers plugins, is measured
# too. Each process writes a data file of its own, and combine merges
# them before the report enforces 100% of statements and branches.
coverage: ## Run the tests and enforce 100% coverage
	uv run coverage erase
	uv run coverage run -m pytest
	uv run coverage combine
	uv run coverage report

check: lint lint-md types coverage ## The full pre-merge gate

build: ## Build the sdist and wheel, then check what they carry
	rm -rf dist
	uv build
	uv run --no-project --with twine twine check dist/*
	@echo "built; publishing happens in CI on a version tag"

spec-sync: ## Refresh the vendored definition from assert-spec
	@./tools/spec-sync.sh src/dokimi_assert/conformance/spec python

.PHONY: spec-check
spec-check: ## Check the vendored definition is intact and say if it is behind
	@./tools/spec-check.sh src/dokimi_assert/conformance/spec
