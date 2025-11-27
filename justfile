# InfraFoundry - Infrastructure Automation Framework
# Command runner using just (https://just.systems)

# Default recipe to display help
default:
    @just --list

# Display help information
help:
    @echo "InfraFoundry - Infrastructure Automation Framework"
    @echo ""
    @echo "Setup commands:"
    @echo "  just install       Install dependencies with uv"
    @echo "  just dev           Install with dev dependencies"
    @echo "  just clean         Remove build artifacts and caches"
    @echo "  just setup-vscode  Display VS Code extension installation tips"
    @echo ""
    @echo "Development commands:"
    @echo "  just test          Run pytest"
    @echo "  just coverage      Run tests with full coverage report"
    @echo "  just lint          Run ruff linter"
    @echo "  just format        Format code with ruff"
    @echo "  just check         Run all checks (lint + type check)"
    @echo ""
    @echo "Infrastructure commands:"
    @echo "  just plan ENV      Generate and plan infrastructure (dry-run)"
    @echo "  just apply ENV     Apply infrastructure changes"
    @echo "  just destroy ENV   Destroy infrastructure"

# Install dependencies with uv
install:
    uv pip install -e .

# Install with dev dependencies
dev:
    uv pip install -e ".[dev]"

# Remove build artifacts and caches
clean:
    rm -rf build/ dist/ *.egg-info __pycache__ .pytest_cache .mypy_cache .ruff_cache tmp/htmlcov/ tmp/coverage.xml tmp/.coverage tmp/.pytest_cache tmp/.mypy_cache tmp/.ruff_cache
    find . -type d -name __pycache__ -exec rm -rf {} +
    find . -type f -name "*.pyc" -delete

# Run pytest
test:
    pytest -v

# Run tests with full coverage report
coverage:
    pytest --cov=src/infrafoundry --cov-report=term-missing --cov-report=html:tmp/htmlcov --cov-report=xml:tmp/coverage.xml -v
    @echo ""
    @echo "Coverage report generated:"
    @echo "  HTML: tmp/htmlcov/index.html"
    @echo "  XML:  tmp/coverage.xml"
    @echo ""
    @echo "Target: 90% coverage (currently ~92%)"

# Run unit tests only
test-unit:
    pytest -v -m unit tests/unit/

# Run integration tests only
test-integration:
    pytest -v -m integration tests/integration/

# Run tests with coverage (alternative)
test-coverage:
    pytest -v --cov=infrafoundry --cov-report=html --cov-report=term-missing
    @echo "Coverage report generated in htmlcov/index.html"

# Run fast tests (skip slow ones)
test-fast:
    pytest -v -m "not slow"

# Run ruff linter
lint:
    ruff check src/ tests/

# Format code with ruff
format:
    ruff format src/ tests/
    ruff check --fix src/ tests/

# Run all checks (lint + type check)
check: lint
    mypy src/

# Generate and plan infrastructure (dry-run)
plan ENV:
    infra plan --env {{ENV}} --dry-run

# Apply infrastructure changes
apply ENV:
    infra apply --env {{ENV}}

# Destroy infrastructure
destroy ENV:
    infra destroy --env {{ENV}}

# Display VS Code extension installation tips
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
