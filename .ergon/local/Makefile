# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

# The targets of assert-python, which ergon init appends to the Makefile. api-docs writes the API
# reference of the README from the code, and make generate runs it. coverage runs the tests under
# coverage and fails below 100% of the statements and branches. check-python runs it on Linux.

##@ Repository

.PHONY: api-docs coverage

api-docs: ## Write the API reference of the README from the code
	$(UV) run --locked python tools/api_reference.py --write

# coverage run starts measuring before Python imports anything, so the plugin, which pytest imports
# while it registers plugins, is measured too. Each process writes a data file of its own, and
# combine merges them before the report enforces 100% of statements and branches.
coverage: ## Run the tests under coverage, and fail below 100% of the statements and branches
	$(UV) run --locked coverage erase
	$(UV) run --locked coverage run -m pytest
	$(UV) run --locked coverage combine
	$(UV) run --locked coverage report

# Windows skips the tests of permission bits and of long names, and a test that a system skips
# leaves a branch that no test takes there. check-python measures the coverage on Linux alone.
ifeq ($(shell uname -s),Linux)
check-python: coverage
endif
