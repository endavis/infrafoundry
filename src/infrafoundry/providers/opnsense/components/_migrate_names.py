"""Names already in an environment, for ``config migrate`` handle assignment (#1337).

``ConfigManager.get_all_resources_all_providers`` requires ``provider:name`` to be
unique across every resource type. A migrate that synthesizes names (certificate
common-name slugs, host-override ``<host>-<domain>`` names) must therefore know the
names the environment already holds. This helper reads them through the same loader
the duplicate check runs over.
"""

from __future__ import annotations

import warnings
from collections.abc import Collection
from pathlib import Path

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.provider import ResourceConfig


def env_provider_resources(
    config_dir: Path, env_name: str, provider_name: str
) -> list[ResourceConfig]:
    """Return every resource of ``provider_name`` in the environment.

    Args:
        config_dir: Configuration directory.
        env_name: Active environment name.
        provider_name: Provider identifier, for example ``opnsense``.

    Returns:
        The provider's resources from every file and package; empty for a missing
        environment.

    Raises:
        DuplicateResourceNameError: If the environment already holds duplicate names.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        resources = ConfigManager(config_dir).get_all_resources_all_providers(env_name)
    return [r for r in resources if r.provider == provider_name]


def reserved_names(resources: list[ResourceConfig], *, exclude_types: Collection[str]) -> set[str]:
    """Return the names of ``resources`` whose type is not in ``exclude_types``.

    Args:
        resources: Resources of one provider.
        exclude_types: Dotted types whose names are not reserved.

    Returns:
        The set of reserved names.
    """
    return {r.name for r in resources if r.type not in exclude_types}
