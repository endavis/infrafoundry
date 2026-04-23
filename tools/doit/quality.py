"""Code quality-related doit tasks."""

from typing import Any

from doit.tools import title_with_actions

from .base import optional_root_files, success_message


def task_lint() -> dict[str, Any]:
    """Run ruff linting."""
    return {
        "actions": ["uv run ruff check src/ tests/ tools/" + optional_root_files("bootstrap.py")],
        "title": title_with_actions,
        "verbosity": 0,
    }


def task_format() -> dict[str, Any]:
    """Format code with ruff."""
    extras = optional_root_files("bootstrap.py")
    return {
        "actions": [
            "uv run ruff format src/ tests/ tools/" + extras,
            "uv run ruff check --fix src/ tests/ tools/" + extras,
        ],
        "title": title_with_actions,
    }


def task_format_check() -> dict[str, Any]:
    """Check code formatting without modifying files."""
    return {
        "actions": [
            "uv run ruff format --check src/ tests/ tools/" + optional_root_files("bootstrap.py")
        ],
        "title": title_with_actions,
        "verbosity": 0,
    }


def task_type_check() -> dict[str, Any]:
    """Run mypy type checking (uses pyproject.toml configuration)."""
    return {
        "actions": ["uv run mypy src/" + optional_root_files("bootstrap.py")],
        "title": title_with_actions,
        "verbosity": 0,
    }


def task_deadcode() -> dict[str, Any]:
    """Detect dead code with vulture (uses pyproject.toml configuration)."""
    return {
        "actions": ["uv run vulture"],
        "title": title_with_actions,
    }


def task_complexity() -> dict[str, Any]:
    """Analyze cyclomatic complexity with radon (A-F grades, A is best)."""
    return {
        "actions": ["uv run radon cc src/ -a -s"],
        "title": title_with_actions,
    }


def task_maintainability() -> dict[str, Any]:
    """Analyze maintainability index with radon (A-F grades, A is best)."""
    return {
        "actions": ["uv run radon mi src/ -s"],
        "title": title_with_actions,
    }


def task_lint_blueprints() -> dict[str, Any]:
    """Lint blueprint scripts for portability contract violations.

    Enforces docs/development/blueprint-script-portability.md by scanning
    blueprints/**/*.sh for tools (currently `jq`, `yq`) that are
    not-recommended on remote hosts. See the docs page for the exemption
    marker if a violation is justified.
    """
    return {
        "actions": ["uv run python tools/lint_blueprint_portability.py"],
        "title": title_with_actions,
        "verbosity": 0,
    }


def task_check() -> dict[str, Any]:
    """Run all checks (format, lint, type check, security, spelling, test)."""
    return {
        "actions": [success_message],
        "task_dep": [
            "format_check",
            "lint",
            "lint_blueprints",
            "type_check",
            "security",
            "spell_check",
            "test",
        ],
        "title": title_with_actions,
    }
