"""Shared ``secret://`` resolution for OPNsense list managers (ADR-0014, #805).

Loads the environment's secret tree once, resolves every ``secret://env_secrets/...``
URI in the config of the resources of one type, and returns copies. The originals
are untouched. Used by the ``system_users``, ``openvpn_instances`` and ``virtual_ip``
managers; tests patch ``_secrets.ConfigManager``.
"""

from __future__ import annotations

from pathlib import Path

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.secrets.resolver import SecretResolver


def resolve_resource_secrets(
    config_dir: Path,
    env_name: str,
    resources: list[ResourceConfig],
    resource_type: str,
) -> list[ResourceConfig]:
    """Resolve ``secret://`` URIs in the configs of ``resource_type`` resources.

    Args:
        config_dir: Configuration directory.
        env_name: Active environment name.
        resources: Resources to process; other types are forwarded unchanged.
        resource_type: The dotted type whose configs are resolved.

    Returns:
        New resource list with secrets resolved to plaintext.

    Raises:
        SecretResolutionError: If a URI cannot be resolved.
    """
    if not any(r.type == resource_type for r in resources):
        return list(resources)
    env_config = ConfigManager(config_dir).load_environment(env_name)
    env_secrets = env_config.secrets if env_config.secrets is not None else {}
    resolver = SecretResolver()
    resolver.configure_backend("env_secrets", {"secrets": env_secrets})
    try:
        resolved: list[ResourceConfig] = []
        for resource in resources:
            if resource.type != resource_type:
                resolved.append(resource)
                continue
            resolved.append(
                ResourceConfig(
                    name=resource.name,
                    type=resource.type,
                    provider=resource.provider,
                    config=resolver.resolve_config(resource.config),
                )
            )
        return resolved
    finally:
        resolver.close()
