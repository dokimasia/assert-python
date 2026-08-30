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

# -p no:dokimi_assert turns this package's own pytest plugin off for
# the outer run. A plugin is imported during plugin registration,
# which happens before pytest-cov starts measuring, so leaving it on
# reports every module it pulls in as barely covered. The plugin is
# still exercised: tests/test_pytest_plugin.py runs pytest inside
# pytest, and those runs load it normally.
coverage: ## Run the tests and enforce the floor
	uv run pytest -p no:dokimi_assert \
		--cov=dokimi_assert --cov-report=term-missing --cov-fail-under=95

check: lint lint-md types coverage ## The full pre-merge gate

build: ## Build the sdist and wheel, then check what they carry
	rm -rf dist
	uv build
	uv run --no-project --with twine twine check dist/*
	@echo "built; publishing happens in CI on a version tag"

spec-sync: ## Refresh the vendored definition from ../assert-spec
	@test -d ../assert-spec || { echo "spec-sync: ../assert-spec not found"; exit 1; }
	cp ../assert-spec/spec/assertions.json src/dokimi_assert/conformance/spec/assertions.json
	cp ../assert-spec/spec/naming.json     src/dokimi_assert/conformance/spec/naming.json
	cp ../assert-spec/overlays/python.json src/dokimi_assert/conformance/spec/overlay.json
	cp ../assert-spec/VERSION              src/dokimi_assert/conformance/spec/VERSION
	rm -rf src/dokimi_assert/conformance/spec/corpus
	cp -r ../assert-spec/corpus src/dokimi_assert/conformance/spec/corpus
