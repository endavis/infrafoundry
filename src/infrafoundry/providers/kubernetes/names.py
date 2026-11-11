"""Kubernetes object name resolution shared by the provider and the validator."""

from __future__ import annotations

from infrafoundry.core.provider import ResourceConfig

CONFIG_NAME_TYPES: frozenset[str] = frozenset(
    {"namespaces", "configmaps", "deployments", "services"}
)


def kubernetes_object_name(resource: ResourceConfig) -> str:
    """Return the Kubernetes object name a resource declares.

    Namespaces, configmaps, deployments and services use ``config.name`` (falling back to
    the top-level ``name`` when missing); every other type uses the top-level ``name``.

    Args:
        resource: Resource to resolve.

    Returns:
        The object name.
    """
    if resource.type in CONFIG_NAME_TYPES:
        return str(resource.config.get("name", resource.name))
    return resource.name
