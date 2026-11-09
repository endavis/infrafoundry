"""Virtual-IP component manager for OPNsense (ADR-0014, #723).

Mirrors the layout of ``components/static_route.py`` and the rest of the
direct-API component family. The unique aspect of this manager is that
it carries secrets: CARP passwords flow via
``secret://env_secrets/<dotted/path>`` URIs.

Resolution flow:

1. The manager passes its resources to the shared
   ``_secrets.resolve_resource_secrets`` helper, which loads the
   environment's decrypted secrets and resolves every URI in each
   resource's config (it returns early, loading nothing, when there are
   no resources).
2. The resolved resources are passed into the existing parser
   (``virtual_ip_configs_from_resources``); the service layer never
   sees the original secret URIs.

Failure modes:

- If a referenced secret path is missing, the helper raises
  ``SecretResolutionError``; the manager surfaces that to the runner
  so the plan/apply outcome carries ``error``.
"""

from __future__ import annotations

from typing import Any, ClassVar

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..services.virtual_ip import (
    Diff,
    LiveVirtualIP,
    VirtualIPConfig,
    VirtualIPService,
    virtual_ip_configs_from_resources,
)
from ._managed import managed_keys as derive_managed_keys
from ._secrets import resolve_resource_secrets
from .base import BaseComponentManager

_TYPE = "interfaces.virtual_ips"


class VirtualIPManager(BaseComponentManager):
    """Manager for virtual-IP component operations.

    Each public method instantiates a ``VirtualIPService`` from the
    environment, resolves any secret URIs in each resource's config,
    and delegates the diff/apply to the service. Errors propagate to
    the caller; the runner is responsible for translating exceptions
    into ``PlanResult.error``/``ApplyResult.error``.
    """

    #: Deletes are limited to the rows InfraFoundry applied before (ADR-0018).
    DELETE_SCOPE: ClassVar[str] = "managed_set"

    #: The runner deletes in a separate phase before this type's adds and updates,
    #: so a row is deleted while the objects it depends on are still live (#1269).
    SPLIT_DELETE_PHASE: ClassVar[bool] = True

    # ------------------------------------------------------------------
    # Plan / apply / destroy
    # ------------------------------------------------------------------

    def plan(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        add_only: bool = False,
        managed_resources: list[ResourceConfig] | None = None,
        provider_name: str = "opnsense",
    ) -> Diff:
        """Compute the add/update/delete diff for the given resources.

        Args:
            env_name: Active environment name.
            resources: Virtual-IP ``ResourceConfig`` entries (filtered upstream).
            add_only: If True, suppress deletes for live VIPs not in YAML.
            managed_resources: Rows InfraFoundry applied before (ADR-0018). When given,
                only live objects matching them may be deleted; ``None`` deletes every
                live object missing from YAML.
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
        return service.compute_diff(
            desired,
            live,
            add_only=add_only,
            managed_keys=derive_managed_keys(
                managed_resources,
                virtual_ip_configs_from_resources,
                type_name="interfaces.virtual_ips",
            ),
        )

    def apply(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        auto_approve: bool = True,
        add_only: bool = False,
        deletes_only: bool = False,
        managed_resources: list[ResourceConfig] | None = None,
        provider_name: str = "opnsense",
    ) -> dict[str, Any]:
        """Apply the diff: add/update/delete virtual IPs and reconfigure.

        Args:
            env_name: Active environment name.
            resources: Virtual-IP ``ResourceConfig`` entries.
            auto_approve: Currently a no-op; the diff engine is the gate.
            add_only: If True, suppress deletes.
            deletes_only: If True, only delete: the runner's delete phase, run
                before the adds and updates (#1269).
            managed_resources: Rows InfraFoundry applied before (ADR-0018). When given,
                only live objects matching them may be deleted; ``None`` deletes every
                live object missing from YAML.
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
        unresolved_managed: set[str] = set()
        diff = service.compute_diff(
            desired,
            live,
            add_only=add_only,
            managed_keys=derive_managed_keys(
                managed_resources,
                virtual_ip_configs_from_resources,
                type_name="interfaces.virtual_ips",
                unresolved=unresolved_managed,
            ),
        )

        if deletes_only:
            diff.adds = []
            diff.updates = []

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
            "unresolved_managed": sorted(unresolved_managed),
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

        Delegates to the shared ``_secrets.resolve_resource_secrets``
        helper, which resolves ``secret://env_secrets/<path>`` URIs in
        every resource's ``config`` against the env's secret tree.

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
        resolved_resources = resolve_resource_secrets(self.config_dir, env_name, resources, _TYPE)
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
