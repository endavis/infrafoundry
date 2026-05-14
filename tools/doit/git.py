"""Git-related doit tasks."""

from typing import Any

from doit.tools import title_with_actions

from .base import install_check_or_skip


def task_commit() -> dict[str, Any]:
    """Interactive commit with commitizen (ensures conventional commit format)."""
    return {
        "actions": [
            install_check_or_skip(
                "commitizen",
                "commitizen not installed. Run: uv sync",
            )
            + "uv run cz commit"
        ],
        "title": title_with_actions,
    }


def task_bump() -> dict[str, Any]:
    """Bump version automatically based on conventional commits."""
    return {
        "actions": [
            install_check_or_skip(
                "commitizen",
                "commitizen not installed. Run: uv sync",
            )
            + "uv run cz bump"
        ],
        "title": title_with_actions,
    }


def task_changelog() -> dict[str, Any]:
    """Generate CHANGELOG from conventional commits."""
    return {
        "actions": [
            install_check_or_skip(
                "commitizen",
                "commitizen not installed. Run: uv sync",
            )
            + "uv run cz changelog"
        ],
        "title": title_with_actions,
    }


def task_pre_commit_install() -> dict[str, Any]:
    """Install pre-commit hooks."""
    return {
        "actions": [
            "uv run pre-commit install",
            "uv run pre-commit install --hook-type post-merge",
            "uv run pre-commit install --hook-type post-checkout",
        ],
        "title": title_with_actions,
    }


def task_pre_commit_run() -> dict[str, Any]:
    """Run pre-commit on all files."""
    return {
        "actions": ["uv run pre-commit run --all-files"],
        "title": title_with_actions,
    }
