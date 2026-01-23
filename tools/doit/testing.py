"""Testing-related doit tasks."""

from typing import Any

from doit.tools import title_with_actions


def task_test() -> dict[str, Any]:
    """Run pytest."""
    return {
        "actions": ["uv run pytest -v"],
        "title": title_with_actions,
        "verbosity": 0,
    }


def task_coverage() -> dict[str, Any]:
    """Run pytest with coverage."""
    return {
        "actions": [
            "uv run pytest "
            "--cov=infrafoundry --cov-report=term-missing "
            "--cov-report=html:tmp/htmlcov --cov-report=xml:tmp/coverage.xml -v"
        ],
        "title": title_with_actions,
    }


def task_test_integration() -> dict[str, Any]:
    """Run integration tests only."""
    return {
        "actions": ["uv run pytest -v -m integration tests/integration/"],
        "title": title_with_actions,
    }
