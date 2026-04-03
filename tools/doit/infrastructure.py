"""InfraFoundry infrastructure management tasks."""

from typing import Any

from doit.tools import title_with_actions


def task_plan() -> dict[str, Any]:
    """Generate and plan infrastructure (dry-run)."""
    return {
        "actions": ["infra plan --env %(env)s --dry-run"],
        "params": [{"name": "env", "short": "e", "default": "dev", "help": "Environment name"}],
        "title": title_with_actions,
    }


def task_apply() -> dict[str, Any]:
    """Apply infrastructure changes."""
    return {
        "actions": ["infra apply --env %(env)s"],
        "params": [{"name": "env", "short": "e", "default": "dev", "help": "Environment name"}],
        "title": title_with_actions,
    }


def task_destroy() -> dict[str, Any]:
    """Destroy infrastructure."""
    return {
        "actions": ["infra destroy --env %(env)s"],
        "params": [{"name": "env", "short": "e", "default": "dev", "help": "Environment name"}],
        "title": title_with_actions,
    }
