# Mailbox Makefile — all commands run through `uv`, which manages the .venv.
# Override the runner with e.g. `make test UV="uv run --no-sync"`.
UV ?= uv run

.PHONY: help
help:
	@echo "Mailbox project Makefile commands:"
	@echo ""
	@echo "Setup:"
	@echo "  make bootstrap      - Install everything needed for development"
	@echo "  make install        - Sync dependencies into the venv (uv sync)"
	@echo ""
	@echo "Testing:"
	@echo "  make test           - Run the fast test suite (excludes integration)"
	@echo "  make test-all       - Run the full suite (includes integration)"
	@echo "  make test-cov       - Run tests with a coverage report"
	@echo "  make test-module M= - Run a single test module/class/test"
	@echo "                        e.g. make test-module M=tests/test_client.py"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint           - Format and lint code (auto-fixes issues)"
	@echo "  make typecheck      - Check Python types with mypy"
	@echo "  make quality        - Lint + typecheck (run before committing)"
	@echo "  make precommit      - Run all pre-commit hooks"
	@echo ""
	@echo "Documentation:"
	@echo "  make agent-docs     - Regenerate CLAUDE.md and AGENTS.md from source"

.PHONY: bootstrap
bootstrap: install
	$(UV) pre-commit install
	@test -f .env || cp .env.example .env
	@echo "Bootstrap complete. Edit .env to add your Kit API key."

.PHONY: install
install:
	uv sync

.PHONY: test
test:
	$(UV) pytest -m "not integration"

.PHONY: test-all
test-all:
	$(UV) pytest

.PHONY: test-cov
test-cov:
	$(UV) pytest -m "not integration" --cov --cov-report=term-missing

.PHONY: test-module
test-module:
ifndef M
	$(error Usage: make test-module M=tests/test_client.py)
endif
	$(UV) pytest $(M)

.PHONY: lint
lint:
	$(UV) ruff format .
	$(UV) ruff check . --fix

.PHONY: typecheck
typecheck:
	$(UV) mypy flipmail

.PHONY: quality
quality: lint typecheck
	@echo "All quality checks passed!"

.PHONY: precommit
precommit:
	@echo "Running pre-commit checks..."
	$(UV) pre-commit run --all-files

.PHONY: agent-docs
agent-docs:
	$(UV) python scripts/build_agent_docs.py
