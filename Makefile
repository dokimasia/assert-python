.PHONY: help install fmt lint types test check spec-sync

help: ## Show this help
	@grep -hE '^[a-z-]+:.*?##' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  %-12s %s\n", $$1, $$2}'

install: ## Create the environment and install the project
	uv sync --extra dev

fmt: ## Format the source
	uv run ruff format src tests
	uv run ruff check --fix src tests

lint: ## Lint, and check formatting without changing anything
	uv run ruff check src tests
	uv run ruff format --check src tests

types: ## Type-check with mypy and with the editor's language server
	uv run mypy
	uv run basedpyright src tests

test: ## Run the tests
	uv run pytest

coverage: ## Run the tests and enforce the floor
	uv run pytest --cov=dokimi --cov-report=term-missing --cov-fail-under=95

check: lint types coverage ## The full pre-merge gate

spec-sync: ## Refresh the vendored definition from ../assert-spec
	@test -d ../assert-spec || { echo "spec-sync: ../assert-spec not found"; exit 1; }
	cp ../assert-spec/spec/assertions.json src/dokimi/conformance/spec/assertions.json
	cp ../assert-spec/spec/naming.json     src/dokimi/conformance/spec/naming.json
	cp ../assert-spec/VERSION              src/dokimi/conformance/spec/VERSION
	rm -rf src/dokimi/conformance/spec/corpus
	cp -r ../assert-spec/corpus src/dokimi/conformance/spec/corpus
