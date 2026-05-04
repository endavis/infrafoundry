"""Virtual-IP component manager for OPNsense (ADR-0014, #723).

Mirrors the layout of ``components/static_route.py`` and the rest of the
direct-API component family. The unique aspect of this manager is that
it is the first direct-API component to carry secrets: CARP passwords
flow via ``secret://env_secrets/<dotted/path>`` URIs which are resolved
by ``SecretResolver`` against an ``EnvSecretsBackend`` configured with
``EnvironmentConfig.secrets`` (populated by
``SecretManager.populate_environment_config`` after SOPS decryption).

Resolution flow (per the issue plan):

1. The manager loads the ``EnvironmentConfig`` for the active env.
2. It instantiates a ``SecretResolver`` and configures the
   ``env_secrets`` backend with ``{"secrets": env_config.secrets}``.
3. For each ``ResourceConfig``, ``resolver.resolve_config()`` is called
   on ``resource.config`` to produce a plaintext-resolved dict.
4. The resolved dicts are passed into the existing parser
   (``virtual_ip_configs_from_resources``); the service layer never
   sees the original secret URIs.

Failure modes:

- If ``env_config.secrets`` is empty (or missing the path the URI
  references), ``SecretResolver.resolve_config`` raises
  ``SecretResolutionError``; the manager surfaces that to the runner
  so plan/apply outcome carries ``error``.
"""

from __future__ import annotations

from typing import Any

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome
from infrafoundry.secrets.resolver import SecretResolver

from ..services.virtual_ip import (
    Diff,
    LiveVirtualIP,
    VirtualIPConfig,
    VirtualIPService,
    virtual_ip_configs_from_resources,
)
from .base import BaseComponentManager


class VirtualIPManager(BaseComponentManager):
    """Manager for virtual-IP component operations.

    Each public method instantiates a ``VirtualIPService`` from the
    environment, resolves any secret URIs in each resource's config,
    and delegates the diff/apply to the service. Errors propagate to
    the caller; the runner is responsible for translating exceptions
    into ``PlanResult.error``/``ApplyResult.error``.
    """

    # ------------------------------------------------------------------
    # Plan / apply / destroy
    # ------------------------------------------------------------------

    def plan(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        add_only: bool = False,
        provider_name: str = "opnsense",
    ) -> Diff:
        """Compute the add/update/delete diff for the given resources.

        Args:
            env_name: Active environment name.
            resources: Virtual-IP ``ResourceConfig`` entries (filtered upstream).
            add_only: If True, suppress deletes for live VIPs not in YAML.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            ``Diff`` describing what apply would do.

        Raises:
            SecretResolutionError: If any ``secret://`` URI cannot be
                resolved against ``env_config.secrets``.
        """
        service = VirtualIPService.from_environment(env_name, provider_name, self.config_dir)
        desired = self._resolve_and_parse(env_name, resources)
        live = service.search()
        return service.compute_diff(desired, live, add_only=add_only)

    def apply(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        auto_approve: bool = True,
        add_only: bool = False,
        provider_name: str = "opnsense",
    ) -> dict[str, Any]:
        """Apply the diff: add/update/delete virtual IPs and reconfigure.

        Args:
            env_name: Active environment name.
            resources: Virtual-IP ``ResourceConfig`` entries.
            auto_approve: Currently a no-op; the diff engine is the gate.
            add_only: If True, suppress deletes.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            Dict with ``resources_created``, ``resources_updated``,
            ``resources_deleted`` counts and a ``resource_outcomes`` list.

        Raises:
            SecretResolutionError: If any ``secret://`` URI cannot be
                resolved against ``env_config.secrets``.
        """
        del auto_approve  # diff engine is the gate; flag accepted for protocol shape
        service = VirtualIPService.from_environment(env_name, provider_name, self.config_dir)
        desired = self._resolve_and_parse(env_name, resources)
        live = service.search()
        diff = service.compute_diff(desired, live, add_only=add_only)

        outcomes: list[ResourceOutcome] = []
        for vip in diff.adds:
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_virtual_ip.{vip.name}",
                    action="add",
                    resource_name=vip.name,
                )
            )

        for _live_vip, want in diff.updates:
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_virtual_ip.{want.name}",
                    action="update",
                    resource_name=want.name,
                )
            )

        for live_vip in diff.deletes:
            synthetic_name = _synthetic_name(live_vip)
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_virtual_ip.{synthetic_name}",
                    action="delete",
                    resource_name=synthetic_name,
                )
            )

        counts = service.apply_diff(diff)
        return {
            "success": True,
            "resources_created": counts["created"],
            "resources_updated": counts["updated"],
            "resources_deleted": counts["deleted"],
            "resource_outcomes": outcomes,
        }

    def destroy(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        auto_approve: bool = True,
        provider_name: str = "opnsense",
    ) -> dict[str, Any]:
        """Delete every live VIP whose tuple is in ``resources``.

        Locked entries are honored: ``lock: true`` resources are skipped
        and counted in the response under ``locked_skipped``.

        Args:
            env_name: Active environment name.
            resources: Virtual-IP ``ResourceConfig`` entries to destroy.
            auto_approve: Currently a no-op.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            Dict with ``resources_destroyed`` and ``locked_skipped`` counts.
        """
        del auto_approve
        service = VirtualIPService.from_environment(env_name, provider_name, self.config_dir)
        desired = self._resolve_and_parse(env_name, resources)
        live = service.search()

        # Index live by natural-key tuple.
        live_by_key: dict[tuple[str, str, str, str], LiveVirtualIP] = {
            entry.diff_key: entry for entry in live
        }

        deleted = 0
        locked_skipped = 0
        any_action = False
        for vip in desired:
            if vip.lock:
                locked_skipped += 1
                continue
            existing = live_by_key.get(vip.diff_key)
            if existing is None:
                continue
            service.delete(existing.uuid)
            deleted += 1
            any_action = True

        if any_action:
            service.reconfigure()

        return {
            "success": True,
            "resources_destroyed": deleted,
            "locked_skipped": locked_skipped,
        }

    # ------------------------------------------------------------------
    # State / migration helpers
    # ------------------------------------------------------------------

    def get_resource_ids(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        provider_name: str = "opnsense",
    ) -> dict[str, str]:
        """Return ``{resource_name: opnsense_uuid}`` for live VIPs matching YAML.

        Matches by the natural-key ``(interface, mode, address, vhid)``
        tuple — the operator-facing ``name`` is only used as the dict
        key in the return value.

        Args:
            env_name: Active environment name.
            resources: Virtual-IP ``ResourceConfig`` entries.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            Mapping from operator-facing resource name to OPNsense UUID.
            Resources without a matching live record are omitted.
        """
        service = VirtualIPService.from_environment(env_name, provider_name, self.config_dir)
        desired = self._resolve_and_parse(env_name, resources)
        live = service.search()
        live_by_key: dict[tuple[str, str, str, str], LiveVirtualIP] = {
            entry.diff_key: entry for entry in live
        }

        result: dict[str, str] = {}
        for vip in desired:
            existing = live_by_key.get(vip.diff_key)
            if existing is not None:
                result[vip.name] = existing.uuid
        return result

    # ------------------------------------------------------------------
    # Secret resolution
    # ------------------------------------------------------------------

    def _resolve_and_parse(
        self, env_name: str, resources: list[ResourceConfig]
    ) -> list[VirtualIPConfig]:
        """Resolve ``secret://`` URIs in each resource and parse to ``VirtualIPConfig``.

        Loads ``EnvironmentConfig.secrets`` once via ``ConfigManager``
        and runs every ``virtual_ips`` resource's ``config`` dict
        through ``SecretResolver.resolve_config``. The resolver is
        configured with the ``env_secrets`` backend so URIs of the
        form ``secret://env_secrets/<path>`` are resolved against the
        env's secret tree.

        Args:
            env_name: Active environment name.
            resources: ``ResourceConfig`` entries (will filter to
                ``virtual_ips`` inside the parser).

        Returns:
            List of parsed ``VirtualIPConfig`` entries with secrets
            resolved to plaintext.

        Raises:
            SecretResolutionError: If any ``secret://`` URI cannot be
                resolved.

        Note:
            Defined before ``list()`` so its ``list[VirtualIPConfig]``
            return annotation resolves to ``builtins.list``. After the
            class declares a method named ``list``, mypy's name-resolution
            in subsequent annotations binds ``list`` to that method. See
            ADR-0014 §"Per-component decisions" — virtual_ips is the
            only direct-API component with a private helper after
            ``list()``, hence the ordering quirk.
        """
        # Load env secrets once.
        config_manager = ConfigManager(self.config_dir)
        env_config = config_manager.load_environment(env_name)
        env_secrets = env_config.secrets if env_config.secrets is not None else {}

        # Build a resolver and resolve every resource's config dict.
        resolver = SecretResolver()
        resolver.configure_backend("env_secrets", {"secrets": env_secrets})

        try:
            resolved_resources: list[ResourceConfig] = []
            for resource in resources:
                if resource.type != "virtual_ips":
                    # Forward non-virtual_ips resources unchanged so the
                    # parser sees them and skips them as expected.
                    resolved_resources.append(resource)
                    continue
                # ``ResourceConfig.config`` is typed ``dict[str, Any]``;
                # the parser handles per-field type errors downstream.
                resolved_config = resolver.resolve_config(resource.config)
                resolved_resources.append(
                    ResourceConfig(
                        name=resource.name,
                        type=resource.type,
                        provider=resource.provider,
                        config=resolved_config,
                    )
                )
        finally:
            resolver.close()

        return virtual_ip_configs_from_resources(resolved_resources)

    # ------------------------------------------------------------------
    # State / migration helpers (continued)
    # ------------------------------------------------------------------

    def list(self, env_name: str, *, provider_name: str = "opnsense") -> list[LiveVirtualIP]:
        """Return the live virtual IPs on the OPNsense box.

        Args:
            env_name: Active environment name.
            provider_name: Provider identifier (defaults to ``opnsense``).
        """
        service = VirtualIPService.from_environment(env_name, provider_name, self.config_dir)
        return service.search()

    def migrate(self, env_name: str, *, provider_name: str = "opnsense") -> str:
        """Export the current virtual IPs to InfraFoundry YAML.

        Args:
            env_name: Active environment name.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            YAML string containing the live VIPs in resource-centric
            form. Operator-facing ``name`` is synthesized from the
            ``(interface, mode, address, vhid)`` natural-key tuple — the
            operator can rename freely after import. CARP passwords are
            redacted (placeholder ``secret://`` URI) since OPNsense
            never returns plaintext passwords on read.
        """
        service = VirtualIPService.from_environment(env_name, provider_name, self.config_dir)
        return service.export_to_yaml()


def _synthetic_name(vip: LiveVirtualIP) -> str:
    """Build a stable synthetic name for a live VIP.

    Used when emitting ``ResourceOutcome`` for deletes — the live
    record carries no operator-facing name. Mirrors
    ``services.virtual_ip._synthesize_name`` so plan output and
    migrated YAML use the same convention.
    """
    address_part = vip.address.replace(":", "-").replace(".", "-").replace("/", "-")
    base = f"vip-{vip.mode}-{vip.interface}-{address_part}"
    if vip.mode == "carp" and vip.vhid:
        base = f"{base}-vhid{vip.vhid}"
    return base.lower()
