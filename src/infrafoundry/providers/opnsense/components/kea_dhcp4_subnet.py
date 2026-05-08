"""Kea DHCPv4 subnet component manager for OPNsense (ADR-0014, #777).

Implements the standard ``plan`` / ``apply`` / ``destroy`` / ``get_resource_ids``
surface against ``KeaDHCPService`` so that ``OPNsenseDirectRunner`` can dispatch
DHCPv4 subnets alongside the other direct-API components. Replaces the
terraform write path (``opnsense_kea_subnet`` via ``browningluke/opnsense``)
that previously ran under ``generate_terraform()``.

Mirrors :mod:`.kea_dhcp6_subnet` line-for-line; differences are flagged inline:

- Identity is the natural key ``subnet`` (the IPv4 CIDR string, e.g.,
  ``10.0.10.0/24``).
- Wire schema uses **flat** ``option_data_*`` fields (not nested under
  ``option_data`` like DHCPv6), e.g., ``option_data_dns_servers`` /
  ``option_data_routers`` / ``option_data_domain_name`` /
  ``option_data_ntp_servers`` / ``option_data_domain_search`` /
  ``option_data_autocollect``. Confirmed by reading
  ``services/kea_dhcp.py:export_to_yaml`` which already reads these fields.
- The ``add`` API response does not include the new UUID; the manager
  re-runs ``search_dhcpv4_subnets`` after each create to recover it.

Reconfigure semantics:

- This manager **does not** call ``service.reconfigure()`` directly.
  Instead it declares ``FINALIZATION_HOOK = "kea_reconfigure"`` and
  ``OPNsenseDirectRunner`` fires the matching hook from
  ``OPNsenseProvider.get_finalization_hooks()`` exactly once after the
  apply loop, so DHCPv4 + DHCPv6 subnets and reservations share a single
  Kea reconfigure (preserving today's "one reconfigure per plan/apply"
  operational behavior).
"""

from __future__ import annotations

from typing import Any, ClassVar

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..services.kea_dhcp import (
    KeaDHCPService,
    _build_desired_subnet4_fields,
    _drop_non_round_trip_subnet4_fields,
    _extract_subnet4_fields,
    _log_field_diff,
)
from .base import BaseComponentManager


class _Diff:
    """Add/update/delete plan for DHCPv4 subnets.

    Lightweight container shaped after the other direct-API services'
    ``Diff`` dataclasses so the runner's ``_format_plan_summary`` can
    read ``adds``/``updates``/``deletes``/``locked`` and ``is_empty``
    uniformly. ``locked`` is always empty here — DHCPv4 subnets do not
    yet support the per-resource ``lock: true`` annotation; promoting
    it is a separate change.
    """

    def __init__(
        self,
        *,
        adds: list[dict[str, Any]] | None = None,
        updates: list[tuple[str, dict[str, Any]]] | None = None,
        deletes: list[tuple[str, str]] | None = None,
    ) -> None:
        self.adds: list[dict[str, Any]] = adds or []
        self.updates: list[tuple[str, dict[str, Any]]] = updates or []
        self.deletes: list[tuple[str, str]] = deletes or []
        self.locked: list[Any] = []

    @property
    def is_empty(self) -> bool:
        """Return True when there are no add/update/delete operations to apply."""
        return not (self.adds or self.updates or self.deletes)


class KeaDHCPv4SubnetManager(BaseComponentManager):
    """Manager for OPNsense Kea DHCPv4 subnet operations.

    Plan/apply/destroy delegate to ``KeaDHCPService``; the runner is
    responsible for translating exceptions into ``PlanResult.error`` /
    ``ApplyResult.error``. Reconfigure is deferred to the runner's
    finalization-hook plumbing — see module docstring.
    """

    #: Runner-level finalization hook key. Matched against the keys
    #: returned by ``OPNsenseProvider.get_finalization_hooks()``; the
    #: reservation manager declares the same value, and so do the
    #: DHCPv6 subnet/reservation managers, so a single Kea reconfigure
    #: fires per apply regardless of which Kea components changed.
    FINALIZATION_HOOK: ClassVar[str] = "kea_reconfigure"

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
    ) -> _Diff:
        """Compute the add/update/delete diff for the given subnets.

        Args:
            env_name: Active environment name.
            resources: DHCPv4 subnet ``ResourceConfig`` entries (filtered upstream).
            add_only: If True, suppress deletes for live subnets not in YAML.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            ``_Diff`` describing what apply would do.
        """
        service = KeaDHCPService.from_environment(env_name, provider_name, self.config_dir)
        return self._compute_diff(service, resources, add_only=add_only)

    def apply(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        auto_approve: bool = True,
        add_only: bool = False,
        provider_name: str = "opnsense",
    ) -> dict[str, Any]:
        """Apply the diff: add / update / delete DHCPv4 subnets.

        Does **not** call ``service.reconfigure()`` directly — the runner
        fires the ``kea_reconfigure`` finalization hook once after every
        component has applied. This preserves today's "one reconfigure
        per plan/apply" operational behavior across both the subnet and
        reservation managers (DHCPv4 + DHCPv6).

        Args:
            env_name: Active environment name.
            resources: DHCPv4 subnet ``ResourceConfig`` entries.
            auto_approve: Currently a no-op; the diff engine is the gate.
            add_only: If True, suppress deletes.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            Dict with ``resources_created``, ``resources_updated``,
            ``resources_deleted`` counts and a ``resource_outcomes`` list.
        """
        del auto_approve  # diff engine is the gate; flag accepted for protocol shape
        service = KeaDHCPService.from_environment(env_name, provider_name, self.config_dir)

        # Ensure DHCPv4 service is enabled with the required interfaces before
        # we mutate subnets — preserves the legacy provider behavior (the
        # terraform path implicitly enabled the service via the browningluke
        # provider's resource creation).
        required_interfaces = sorted(
            {str(r.config.get("interface")) for r in resources if r.config.get("interface")}
        )
        if required_interfaces:
            service.ensure_dhcpv4_enabled(required_interfaces)

        diff = self._compute_diff(service, resources, add_only=add_only)

        outcomes: list[ResourceOutcome] = []
        created = 0
        updated = 0
        deleted = 0

        for subnet_data in diff.adds:
            subnet_name = str(subnet_data.pop("__name__"))
            result = service.add_dhcpv4_subnet(subnet_data)
            if result.get("result") == "failed":
                raise ValueError(f"Failed to create DHCPv4 subnet {subnet_name}: {result}")
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_kea_subnet.{subnet_name}",
                    action="add",
                    resource_name=subnet_name,
                )
            )
            created += 1

        for uuid, subnet_data in diff.updates:
            subnet_name = str(subnet_data.pop("__name__"))
            service.update_dhcpv4_subnet(uuid, subnet_data)
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_kea_subnet.{subnet_name}",
                    action="update",
                    resource_name=subnet_name,
                )
            )
            updated += 1

        for uuid, subnet_address in diff.deletes:
            service.delete_dhcpv4_subnet(uuid)
            synthetic_name = f"subnet-{subnet_address}"
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_kea_subnet.{synthetic_name}",
                    action="delete",
                    resource_name=synthetic_name,
                )
            )
            deleted += 1

        return {
            "success": True,
            "resources_created": created,
            "resources_updated": updated,
            "resources_deleted": deleted,
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
        """Delete every live subnet whose ``subnet`` CIDR is in ``resources``.

        DHCPv4 subnets do not yet honor a per-resource ``lock`` flag at
        the diff layer; ``locked_skipped`` is always 0 today. Adding
        ``lock`` support is a separate change.

        Args:
            env_name: Active environment name.
            resources: DHCPv4 subnet ``ResourceConfig`` entries to destroy.
            auto_approve: Currently a no-op.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            Dict with ``resources_destroyed`` and ``locked_skipped`` counts.
        """
        del auto_approve
        service = KeaDHCPService.from_environment(env_name, provider_name, self.config_dir)

        existing = service.search_dhcpv4_subnets()
        existing_by_subnet = {str(s.get("subnet", "")): str(s.get("uuid", "")) for s in existing}

        deleted = 0
        for resource in resources:
            subnet_address = str(resource.config.get("subnet", ""))
            uuid = existing_by_subnet.get(subnet_address)
            if not uuid:
                continue
            service.delete_dhcpv4_subnet(uuid)
            deleted += 1

        return {
            "success": True,
            "resources_destroyed": deleted,
            "locked_skipped": 0,
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
        """Return ``{resource_name: opnsense_uuid}`` for live DHCPv4 subnets.

        Matches by the natural-key ``subnet`` CIDR; the operator-facing
        ``name`` is only used as the dict key in the return value.

        Args:
            env_name: Active environment name.
            resources: DHCPv4 subnet ``ResourceConfig`` entries.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            Mapping from operator-facing resource name to OPNsense UUID.
            Resources without a matching live record are omitted.
        """
        service = KeaDHCPService.from_environment(env_name, provider_name, self.config_dir)
        existing = service.search_dhcpv4_subnets()
        existing_by_subnet = {str(s.get("subnet", "")): str(s.get("uuid", "")) for s in existing}

        result: dict[str, str] = {}
        for resource in resources:
            subnet_address = str(resource.config.get("subnet", ""))
            uuid = existing_by_subnet.get(subnet_address)
            if uuid:
                result[resource.name] = uuid
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_diff(
        service: KeaDHCPService,
        resources: list[ResourceConfig],
        *,
        add_only: bool,
    ) -> _Diff:
        """Compute the add/update/delete diff against live state.

        Adds carry the wire-format ``subnet_data`` dict (with the
        operator-facing ``name`` injected as ``__name__`` so ``apply``
        can attribute outcomes); updates carry ``(uuid, subnet_data)``;
        deletes carry ``(uuid, subnet_address)`` for synthetic-name
        construction.
        """
        existing = service.search_dhcpv4_subnets()
        existing_by_subnet = {str(s.get("subnet", "")): str(s.get("uuid", "")) for s in existing}

        adds: list[dict[str, Any]] = []
        updates: list[tuple[str, dict[str, Any]]] = []
        seen_subnets: set[str] = set()

        for resource in resources:
            subnet_data = _build_subnet_payload(resource)
            subnet_address = str(subnet_data["subnet"])
            seen_subnets.add(subnet_address)

            existing_uuid = existing_by_subnet.get(subnet_address)
            if existing_uuid:
                current = service.get_dhcpv4_subnet(existing_uuid)
                current_fields = _extract_subnet4_fields(current)
                desired_fields = _build_desired_subnet4_fields(subnet_data)
                _drop_non_round_trip_subnet4_fields(current_fields, desired_fields)
                if current_fields != desired_fields:
                    _log_field_diff(
                        f"DHCPv4 subnet {resource.name}", current_fields, desired_fields
                    )
                    updates.append(
                        (existing_uuid, {**subnet_data, "__name__": resource.name}),
                    )
            else:
                adds.append({**subnet_data, "__name__": resource.name})

        deletes: list[tuple[str, str]] = []
        if not add_only:
            for subnet_address, uuid in existing_by_subnet.items():
                if subnet_address and subnet_address not in seen_subnets:
                    deletes.append((uuid, subnet_address))

        return _Diff(adds=adds, updates=updates, deletes=deletes)


def _build_subnet_payload(resource: ResourceConfig) -> dict[str, Any]:
    """Build the wire-format payload sent to OPNsense for a DHCPv4 subnet.

    Mirrors the legacy terraform template (``kea_subnet.tf.j2``) field
    coverage so wire-level behavior is unchanged. DHCPv4 uses **flat**
    ``option_data_*`` fields on the wire, distinct from DHCPv6's nested
    ``option_data`` dict.

    Args:
        resource: DHCPv4 subnet resource (validated upstream).

    Returns:
        Dict suitable for passing to ``service.add_dhcpv4_subnet`` /
        ``service.update_dhcpv4_subnet``.
    """
    config = resource.config
    subnet_data: dict[str, Any] = {
        "subnet": config.get("subnet"),
    }

    if "interface" in config:
        subnet_data["interface"] = config["interface"]

    # Pools is a newline-separated string of ranges. The legacy terraform
    # template accepted plain string entries (e.g., "192.168.1.10-192.168.1.99"),
    # not the dict-with-range shape DHCPv6 uses.
    if "pools" in config:
        pool_strings: list[str] = []
        for pool in config["pools"]:
            if isinstance(pool, dict) and "range" in pool:
                pool_strings.append(str(pool["range"]))
            else:
                pool_strings.append(str(pool))
        subnet_data["pools"] = "\n".join(pool_strings)

    if "valid_lifetime" in config:
        subnet_data["valid_lifetime"] = str(config["valid_lifetime"])
    if "description" in config:
        subnet_data["description"] = config["description"]
    if "domain_name" in config:
        subnet_data["domain_name"] = config["domain_name"]

    if "match_client_id" in config:
        subnet_data["match_client_id"] = "1" if config["match_client_id"] else "0"
    if "auto_collect" in config:
        subnet_data["option_data_autocollect"] = "1" if config["auto_collect"] else "0"

    # Flat option_data_* fields — comma-joined strings (DHCPv4 wire shape).
    if "dns_servers" in config:
        subnet_data["option_data_dns_servers"] = ",".join(config["dns_servers"])
    if "routers" in config:
        subnet_data["option_data_routers"] = ",".join(config["routers"])
    if "ntp_servers" in config:
        subnet_data["option_data_ntp_servers"] = ",".join(config["ntp_servers"])
    if "domain_search" in config:
        subnet_data["option_data_domain_search"] = ",".join(config["domain_search"])

    return subnet_data
