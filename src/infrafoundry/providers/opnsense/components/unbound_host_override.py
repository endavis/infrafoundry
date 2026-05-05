"""Unbound host-override component manager for OPNsense (read-side migrate; #748).

Mirrors the migrate-only shape of ``components/alias.py``: no
``plan``/``apply``/``destroy`` because host overrides are still on the
terraform write path (``unbound_host_override.tf.j2``). The single
public entry point is :meth:`UnboundHostOverrideManager.migrate`, which
delegates to :class:`UnboundHostOverrideService.export_to_yaml` for the
``foundry config migrate --component unbound_host_override`` command.

When/if host overrides move to the direct-API write path (separate ADR
decision), this manager will grow the standard ``plan``/``apply``/
``destroy``/``get_resource_ids`` surface that ``OPNsenseDirectRunner``
expects, mirroring ``components/unbound_host_alias.py``. Today it stays
read-only.
"""

from __future__ import annotations

from ..services.unbound_host_override import UnboundHostOverrideService
from .base import BaseComponentManager


class UnboundHostOverrideManager(BaseComponentManager):
    """Read-side manager for OPNsense Unbound host override extraction.

    Exposes only :meth:`migrate` — every call instantiates an
    :class:`UnboundHostOverrideService` from the environment and
    delegates to its ``export_to_yaml``. No state is held between calls.
    """

    def migrate(self, env_name: str, *, provider_name: str = "opnsense") -> str:
        """Export the current Unbound host overrides to InfraFoundry YAML.

        Args:
            env_name: Active environment name.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            YAML string containing the live host overrides in
            resource-centric form. Operator-facing ``name`` is
            synthesized from ``hostname.domain``.
        """
        service = UnboundHostOverrideService.from_environment(
            env_name, provider_name, self.config_dir
        )
        return service.export_to_yaml()
