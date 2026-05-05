"""Alias component manager for OPNsense (read-side migrate; #747).

Mirrors the migrate-only shape of ``components/isc_to_kea_migration.py``:
no ``plan``/``apply``/``destroy`` because aliases are still on the
terraform write path (``aliases.tf.j2``). The single public entry
point is :meth:`AliasManager.migrate`, which delegates to
:class:`AliasService.export_to_yaml` for the
``foundry config migrate --component aliases`` command.

When/if aliases move to the direct-API write path (separate ADR
decision), this manager will grow the standard ``plan``/``apply``/
``destroy``/``get_resource_ids`` surface that ``OPNsenseDirectRunner``
expects, mirroring ``components/unbound_forward.py``. Today it stays
read-only.
"""

from __future__ import annotations

from ..services.alias import AliasService
from .base import BaseComponentManager


class AliasManager(BaseComponentManager):
    """Read-side manager for OPNsense alias extraction.

    Exposes only :meth:`migrate` — every call instantiates an
    :class:`AliasService` from the environment and delegates to its
    ``export_to_yaml``. No state is held between calls.
    """

    def migrate(self, env_name: str, *, provider_name: str = "opnsense") -> str:
        """Export the current aliases to InfraFoundry YAML.

        Args:
            env_name: Active environment name.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            YAML string containing the live aliases in resource-centric
            form. Operator-facing ``name`` is the alias name verbatim.
        """
        service = AliasService.from_environment(env_name, provider_name, self.config_dir)
        return service.export_to_yaml()
