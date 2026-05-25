"""Tailscale subnets component manager for OPNsense (#787).

List-shape component manager for the ``tailscale.subnets`` dotted resource
type — one resource per CIDR subnet to advertise via Tailscale. The wire
side is an embedded list at ``settings.subnets.subnet4``; there is no
per-subnet CRUD endpoint. All subnet writes go through a full-replace of
the embedded list via ``tailscale/settings/set``.

The manager uses :class:`_TailscaleSubnetsDiff` which performs a
sorted-set comparison (desired CIDRs vs live CIDRs) to produce:

- ``adds``: CIDRs present in desired but absent in live.
- ``deletes``: CIDRs present in live but absent in desired.
- ``updates``: always empty (CIDRs are atomic — you either have them or not).

Apply path uses :meth:`TailscaleService.apply_settings_patch` so that
posting the subnets list does NOT clobber the scalar settings fields
(the ``tailscale/settings/set`` endpoint is full-replace; the service
helper handles the read-modify-write).

When ``add_only=True``, deletes are suppressed (ads-only mode).

Reconfiguration is deferred to the runner's ``tailscale_reconfigure``
finalization hook which is shared by all three tailscale managers.
"""

from __future__ import annotations

from typing import Any, ClassVar

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..services.tailscale import TailscaleService
from .base import BaseComponentManager


class _TailscaleSubnetsDiff:
    """Plan-shape adapter for tailscale subnets sorted-set diff.

    Exposes the standard ``adds``/``updates``/``deletes``/``locked`` /
    ``is_empty`` surface that ``OPNsenseDirectRunner._format_plan_summary``
    consumes for plan display.

    - ``adds``: list of CIDR strings to add.
    - ``updates``: always empty — subnets are atomic CIDRs.
    - ``deletes``: list of CIDR strings to remove.
    - ``locked``: always empty.

    Args:
        adds: CIDRs present in desired but absent in live.
        deletes: CIDRs present in live but absent in desired.
    """

    def __init__(
        self,
        *,
        adds: list[str] | None = None,
        deletes: list[str] | None = None,
    ) -> None:
        """Initialize the tailscale subnets diff."""
        self.adds: list[str] = adds or []
        self.updates: list[str] = []
        self.deletes: list[str] = deletes or []
        self.locked: list[Any] = []

    @property
    def is_empty(self) -> bool:
        """Return True when there are no add or delete operations to apply."""
        return not (self.adds or self.deletes)


class TailscaleSubnetsManager(BaseComponentManager):
    """Manager for OPNsense tailscale subnets list operations."""

    #: Shared tailscale finalization hook (#787). Fired once per apply
    #: when any of the three tailscale managers mutated state.
    FINALIZATION_HOOK: ClassVar[str] = "tailscale_reconfigure"

    def plan(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        add_only: bool = False,
        provider_name: str = "opnsense",
    ) -> _TailscaleSubnetsDiff:
        """Compute the sorted-set diff between live subnets and desired YAML entries.

        Args:
            env_name: Active environment name.
            resources: ``tailscale.subnets`` ``ResourceConfig`` list (one
                per CIDR).
            add_only: If True, suppress deletes — only adds are returned.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            ``_TailscaleSubnetsDiff`` with ``adds`` and ``deletes`` CIDR lists.
        """
        service = TailscaleService.from_environment(env_name, provider_name, self.config_dir)
        live_cidrs = set(service.extract_subnet_cidrs(service.get_settings()))
        desired_cidrs = set(service.build_desired_subnet_cidrs(resources))

        adds = sorted(desired_cidrs - live_cidrs)
        deletes = sorted(live_cidrs - desired_cidrs) if not add_only else []
        return _TailscaleSubnetsDiff(adds=adds, deletes=deletes)

    def apply(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        auto_approve: bool = True,
        add_only: bool = False,
        provider_name: str = "opnsense",
    ) -> dict[str, Any]:
        """Apply the subnets diff: full-replace the embedded subnets list.

        Uses :meth:`TailscaleService.apply_settings_patch` (read-modify-write)
        so the subnets payload does not clobber the scalar settings fields.

        When ``add_only=True``, the desired CIDR set is unioned with the live
        set so no existing subnets are removed.

        Does NOT call ``service.reconfigure()`` — the runner fires the
        ``tailscale_reconfigure`` finalization hook once after all three
        tailscale managers have applied.

        Args:
            env_name: Active environment name.
            resources: ``tailscale.subnets`` ``ResourceConfig`` list.
            auto_approve: No-op.
            add_only: If True, existing subnets are preserved (only adds).
            provider_name: Provider identifier.

        Returns:
            Dict with counts and ``resource_outcomes``. One outcome per
            added CIDR and one per deleted CIDR.
        """
        del auto_approve
        service = TailscaleService.from_environment(env_name, provider_name, self.config_dir)
        diff = self.plan(env_name, resources, add_only=add_only, provider_name=provider_name)

        if diff.is_empty:
            return {
                "success": True,
                "resources_created": 0,
                "resources_updated": 0,
                "resources_deleted": 0,
                "resource_outcomes": [],
            }

        # Compute the final desired list: adds minus deletes from live.
        live_cidrs = set(service.extract_subnet_cidrs(service.get_settings()))
        desired_cidrs = set(service.build_desired_subnet_cidrs(resources))
        final_cidrs = sorted(live_cidrs | desired_cidrs) if add_only else sorted(desired_cidrs)

        wire = service.build_subnets_wire_payload(final_cidrs)
        service.apply_settings_patch(wire)

        outcomes: list[ResourceOutcome] = []
        for cidr in diff.adds:
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_tailscale_subnets.{cidr}",
                    action="add",
                    resource_name=cidr,
                )
            )
        for cidr in diff.deletes:
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_tailscale_subnets.{cidr}",
                    action="delete",
                    resource_name=cidr,
                )
            )

        return {
            "success": True,
            "resources_created": len(diff.adds),
            "resources_updated": 0,
            "resources_deleted": len(diff.deletes),
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
        """No-op: tailscale subnets are managed declaratively; destroy is a no-op.

        The router advertisement subnets list is cleared by removing
        subnet entries from YAML and re-applying; there is no "destroy"
        concept for the embedded list (the OPNsense plugin does not
        have a global disable path for subnets).

        Args:
            env_name: Active environment name (unused).
            resources: ``tailscale.subnets`` resource list (unused).
            auto_approve: No-op.
            provider_name: Provider identifier (unused).

        Returns:
            Empty outcome with ``resources_destroyed=0``.
        """
        del env_name, resources, auto_approve, provider_name
        return {
            "success": True,
            "resources_destroyed": 0,
            "resource_outcomes": [],
        }

    def get_resource_ids(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        provider_name: str = "opnsense",
    ) -> dict[str, str]:
        """Return per-CIDR stable IDs from live state.

        Subnets have no OPNsense UUID — the CIDR itself is the stable
        identity. State tracking records one entry per live CIDR.

        Args:
            env_name: Active environment name.
            resources: ``tailscale.subnets`` resource list (unused).
            provider_name: Provider identifier.

        Returns:
            Mapping like ``{"subnets.192.168.110.0/24": "192.168.110.0/24"}``.
        """
        del resources
        service = TailscaleService.from_environment(env_name, provider_name, self.config_dir)
        live_cidrs = service.extract_subnet_cidrs(service.get_settings())
        return {f"subnets.{cidr}": cidr for cidr in live_cidrs}

    def migrate(
        self,
        env_name: str,
        *,
        provider_name: str = "opnsense",
    ) -> str:
        """Export current tailscale subnets to InfraFoundry YAML.

        Args:
            env_name: Active environment name.
            provider_name: Provider identifier.

        Returns:
            YAML string under the ``opnsense.tailscale.subnets`` namespace.
        """
        service = TailscaleService.from_environment(env_name, provider_name, self.config_dir)
        return service.export_subnets_to_yaml()
