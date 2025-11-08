.PHONY: help install dev clean test coverage lint format check plan apply destroy

help:
	@echo "InfraFoundry - Infrastructure Automation Framework"
	@echo ""
	@echo "Setup commands:"
	@echo "  make install       Install dependencies with uv"
	@echo "  make dev           Install with dev dependencies"
	@echo "  make clean         Remove build artifacts and caches"
	@echo ""
	@echo "Development commands:"
	@echo "  make test          Run pytest"
	@echo "  make coverage      Run tests with full coverage report"
	@echo "  make lint          Run ruff linter"
	@echo "  make format        Format code with black"
	@echo "  make check         Run all checks (lint + type check)"
	@echo ""
	@echo "Infrastructure commands:"
	@echo "  make plan ENV=dev  Generate and plan infrastructure (dry-run)"
	@echo "  make apply ENV=dev Apply infrastructure changes"
	@echo "  make destroy ENV=dev Destroy infrastructure"

install:
	uv pip install -e .

dev:
	uv pip install -e ".[dev]"

clean:
	rm -rf build/ dist/ *.egg-info __pycache__ .pytest_cache .mypy_cache .ruff_cache htmlcov/ coverage.xml .coverage
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

test:
	pytest -v

coverage:
	pytest --cov=src/infrafoundry --cov-report=term-missing --cov-report=html --cov-report=xml --cov-fail-under=69 -v
	@echo ""
	@echo "Coverage report generated:"
	@echo "  HTML: htmlcov/index.html"
	@echo "  XML:  coverage.xml"

test-unit:
	pytest -v -m unit tests/unit/

test-integration:
	pytest -v -m integration tests/integration/

test-coverage:
	pytest -v --cov=infrafoundry --cov-report=html --cov-report=term-missing
	@echo "Coverage report generated in htmlcov/index.html"

test-fast:
	pytest -v -m "not slow"

lint:
	ruff check src/ tests/

format:
	black src/ tests/
	ruff check --fix src/ tests/

check: lint
	mypy src/

plan:
	@if [ -z "$(ENV)" ]; then echo "Error: ENV not set. Usage: make plan ENV=dev"; exit 1; fi
	infra plan --env $(ENV) --dry-run

apply:
	@if [ -z "$(ENV)" ]; then echo "Error: ENV not set. Usage: make apply ENV=dev"; exit 1; fi
	infra apply --env $(ENV)

destroy:
	@if [ -z "$(ENV)" ]; then echo "Error: ENV not set. Usage: make destroy ENV=dev"; exit 1; fi
	infra destroy --env $(ENV)
