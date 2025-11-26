.PHONY: help install dev clean test coverage lint format check plan apply destroy setup-vscode

help:
	@echo "InfraFoundry - Infrastructure Automation Framework"
	@echo ""
	@echo "Setup commands:"
	@echo "  make install       Install dependencies with uv"
	@echo "  make dev           Install with dev dependencies"
	@echo "  make clean         Remove build artifacts and caches"
	@echo "  make setup-vscode  Display VS Code extension installation tips"
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
	rm -rf build/ dist/ *.egg-info __pycache__ .pytest_cache .mypy_cache .ruff_cache tmp/htmlcov/ tmp/coverage.xml .coverage
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

test:
	pytest -v

coverage:
	pytest --cov=src/infrafoundry --cov-report=term-missing --cov-report=html:tmp/htmlcov --cov-report=xml:tmp/coverage.xml -v
	@echo ""
	@echo "Coverage report generated:"
	@echo "  HTML: tmp/htmlcov/index.html"
	@echo "  XML:  tmp/coverage.xml"
	@echo ""
	@echo "Target: 90% coverage (currently ~92%)"

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
	ruff format src/ tests/
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

setup-vscode:
	@echo "VS Code Extensions Setup"
	@echo "========================"
	@echo ""
	@echo "When you open this workspace in VS Code, you'll be prompted to install"
	@echo "recommended extensions. Alternatively, you can:"
	@echo ""
	@echo "1. Press Ctrl+Shift+P (Cmd+Shift+P on Mac)"
	@echo "2. Type 'Extensions: Show Recommended Extensions'"
	@echo "3. Click 'Install All' button"
	@echo ""
	@echo "Recommended extensions include:"
	@echo "  • Python development tools (Pylance, debugpy)"
	@echo "  • Code quality (Ruff, Black)"
	@echo "  • Testing (pytest)"
	@echo "  • Infrastructure (Terraform, Ansible)"
	@echo "  • Git tools (GitLens)"
	@echo ""
	@echo "See .vscode/extensions.json for the complete list."
