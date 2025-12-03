"""Environment configuration diff utilities."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.provider import ResourceConfig


def _to_json(value: Any) -> str:
    """Serialize a value to a stable JSON string for comparison/logging."""
    return json.dumps(value, sort_keys=True, default=str)


def _resource_key(resource: ResourceConfig) -> str:
    """Create a stable key for a resource."""
    return f"{resource.provider}:{resource.name}"


@dataclass
class ConfigDiffResult:
    """Container for environment diff results."""

    env_a: str
    env_b: str
    settings_changes: list[str]
    resources_added: list[str]
    resources_removed: list[str]
    resources_changed: list[str]

    def is_empty(self) -> bool:
        """Return True when no differences exist."""
        return not any(
            [
                self.settings_changes,
                self.resources_added,
                self.resources_removed,
                self.resources_changed,
            ]
        )


def diff_environments(
    config_manager: ConfigManager,
    env_a: str,
    env_b: str,
    provider_filter: str | None = None,
) -> ConfigDiffResult:
    """Compute differences between two environments.

    Args:
        config_manager: Config manager to load environments/resources.
        env_a: First environment name.
        env_b: Second environment name.
        provider_filter: Optional provider name to scope resource comparison.

    Returns:
        ConfigDiffResult detailing settings and resource differences.
    """
    env_a_config = config_manager.load_environment(env_a)
    env_b_config = config_manager.load_environment(env_b)

    settings_changes = _diff_settings(env_a_config, env_b_config)

    resources_a = config_manager.get_all_resources_all_providers(env_a)
    resources_b = config_manager.get_all_resources_all_providers(env_b)

    added, removed, changed = _diff_resources(resources_a, resources_b, provider_filter)

    return ConfigDiffResult(
        env_a=env_a,
        env_b=env_b,
        settings_changes=settings_changes,
        resources_added=added,
        resources_removed=removed,
        resources_changed=changed,
    )


def _diff_settings(env_a: EnvironmentConfig, env_b: EnvironmentConfig) -> list[str]:
    """Compute differences between two EnvironmentConfig objects."""
    dict_a = env_a.model_dump()
    dict_b = env_b.model_dump()

    # Ignore the environment name when comparing.
    ignore_keys = {"name"}

    changes: list[str] = []
    for key in sorted(set(dict_a) | set(dict_b)):
        if key in ignore_keys:
            continue

        if dict_a.get(key) != dict_b.get(key):
            left = _to_json(dict_a.get(key))
            right = _to_json(dict_b.get(key))
            changes.append(f"{key}: {left} -> {right}")

    return changes


def _diff_resources(
    resources_a: list[ResourceConfig],
    resources_b: list[ResourceConfig],
    provider_filter: str | None,
) -> tuple[list[str], list[str], list[str]]:
    """Compare resource collections and return added/removed/changed keys."""
    if provider_filter:
        resources_a = [r for r in resources_a if r.provider == provider_filter]
        resources_b = [r for r in resources_b if r.provider == provider_filter]

    map_a = {_resource_key(res): res for res in resources_a}
    map_b = {_resource_key(res): res for res in resources_b}

    added_keys = sorted(set(map_b) - set(map_a))
    removed_keys = sorted(set(map_a) - set(map_b))

    changed_keys: list[str] = []
    for key in sorted(set(map_a) & set(map_b)):
        a = map_a[key]
        b = map_b[key]

        if a.type != b.type:
            changed_keys.append(key)
            continue

        if _to_json(a.config) != _to_json(b.config):
            changed_keys.append(key)

    return added_keys, removed_keys, changed_keys
