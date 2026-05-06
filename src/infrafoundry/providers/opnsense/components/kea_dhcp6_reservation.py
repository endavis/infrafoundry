"""Kea DHCPv6 reservation component manager for OPNsense (ADR-0014, #758).

Implements the standard ``plan`` / ``apply`` / ``destroy`` /
``get_resource_ids`` surface against ``KeaDHCPService`` so that
``OPNsenseDirectRunner`` can dispatch DHCPv6 reservations alongside the other
direct-API components. Replaces the inline reservation handling in
``OPNsenseProvider._generate_kea_dhcp6_resources`` (#758).

The change-detection helpers used here live at module scope in
``services/kea_dhcp.py`` (relocated in #758, byte-identical move).

Identity / wire schema:

- Identity is the natural key ``(duid, subnet_uuid)`` — the same tuple
  the original ``_generate_kea_dhcp6_resources`` used. ``subnet_uuid`` is
  resolved at apply time by reading ``service.search_dhcpv6_subnets()``
  and matching the operator-facing ``subnet`` field (an IPv6 CIDR) to
  the live subnet UUID. If no live subnet matches, the manager raises
  :class:`ReferenceValidationError` so the failure surfaces at plan
  time rather than as a silent skip-with-warning at apply time
  (a deliberate behavioral upgrade flagged in the #758 plan).
- Wire schema: ``subnet`` (UUID, not the CIDR), ``ip_address``,
  ``duid``, ``hostname``, ``description``.

Reconfigure semantics:

- This manager **does not** call ``service.reconfigure()`` directly.
  It declares ``FINALIZATION_HOOK = "kea_dhcp6_reconfigure"`` (the
  same key as :class:`KeaDHCPv6SubnetManager`) so the runner fires
  exactly one Kea reconfigure even when both subnets and reservations
  changed in the same apply.
"""

from __future__ import annotations

from typing import Any, ClassVar

from infrafoundry.core.exceptions import ReferenceValidationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..services.kea_dhcp import (
    KeaDHCPService,
    _build_desired_reservation_fields,
    _extract_reservation_fields,
    _log_field_diff,
)
from .base import BaseComponentManager


class _Diff:
    """Add/update/delete plan for DHCPv6 reservations.

    Same shape as :class:`.kea_dhcp6_subnet._Diff` so the runner's
    ``_format_plan_summary`` can read the plan summary uniformly across
    every direct-API component.
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


class KeaDHCPv6ReservationManager(BaseComponentManager):
    """Manager for OPNsense Kea DHCPv6 reservation operations."""

    #: Runner-level finalization hook key. Matched against
    #: ``OPNsenseProvider.get_finalization_hooks()``; shared with
    #: :class:`KeaDHCPv6SubnetManager` so a single Kea reconfigure
    #: fires per apply when both managers had changes.
    FINALIZATION_HOOK: ClassVar[str] = "kea_dhcp6_reconfigure"

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
        """Compute the add/update/delete diff for the given reservations.

        Args:
            env_name: Active environment name.
            resources: DHCPv6 reservation ``ResourceConfig`` entries.
            add_only: If True, suppress deletes for live reservations not in YAML.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            ``_Diff`` describing what apply would do.

        Raises:
            ReferenceValidationError: If any reservation references a
                ``subnet`` CIDR that does not match any live DHCPv6 subnet.
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
        """Apply the diff: add / update / delete DHCPv6 reservations.

        Does **not** call ``service.reconfigure()`` directly — see the
        module docstring for the runner-side hook contract.

        Args:
            env_name: Active environment name.
            resources: DHCPv6 reservation ``ResourceConfig`` entries.
            auto_approve: Currently a no-op; the diff engine is the gate.
            add_only: If True, suppress deletes.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            Dict with ``resources_created``, ``resources_updated``,
            ``resources_deleted`` counts and a ``resource_outcomes`` list.

        Raises:
            ReferenceValidationError: If any reservation references a
                ``subnet`` CIDR that does not match any live DHCPv6 subnet.
        """
        del auto_approve
        service = KeaDHCPService.from_environment(env_name, provider_name, self.config_dir)
        diff = self._compute_diff(service, resources, add_only=add_only)

        outcomes: list[ResourceOutcome] = []
        created = 0
        updated = 0
        deleted = 0

        for reservation_data in diff.adds:
            reservation_name = str(reservation_data.pop("__name__"))
            result = service.add_dhcpv6_reservation(reservation_data)
            if result.get("result") == "failed":
                validations = result.get("validations", {})
                raise ValueError(
                    f"Failed to create DHCPv6 reservation {reservation_name}: {validations}"
                )
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_kea_dhcp6_reservation.{reservation_name}",
                    action="add",
                    resource_name=reservation_name,
                )
            )
            created += 1

        for uuid, reservation_data in diff.updates:
            reservation_name = str(reservation_data.pop("__name__"))
            service.update_dhcpv6_reservation(uuid, reservation_data)
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_kea_dhcp6_reservation.{reservation_name}",
                    action="update",
                    resource_name=reservation_name,
                )
            )
            updated += 1

        for uuid, descriptor in diff.deletes:
            service.delete_dhcpv6_reservation(uuid)
            synthetic_name = f"reservation-{descriptor}"
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_kea_dhcp6_reservation.{synthetic_name}",
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
        """Delete every live reservation matching ``resources``.

        Matches by ``(duid, subnet_uuid)`` — the natural-key tuple. The
        ``subnet_uuid`` is resolved from each resource's ``subnet`` CIDR
        via ``search_dhcpv6_subnets`` (mirrors apply-time resolution).

        Args:
            env_name: Active environment name.
            resources: DHCPv6 reservation ``ResourceConfig`` entries to destroy.
            auto_approve: Currently a no-op.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            Dict with ``resources_destroyed`` and ``locked_skipped`` counts.

        Raises:
            ReferenceValidationError: If any reservation references a
                ``subnet`` CIDR that does not match any live DHCPv6 subnet.
        """
        del auto_approve
        service = KeaDHCPService.from_environment(env_name, provider_name, self.config_dir)
        cidr_to_uuid = _build_subnet_cidr_lookup(service)

        live_reservations = service.search_dhcpv6_reservations()
        live_by_key: dict[tuple[str, str], str] = {
            (str(r.get("duid", "")), str(r.get("subnet", ""))): str(r.get("uuid", ""))
            for r in live_reservations
        }

        deleted = 0
        for resource in resources:
            duid = str(resource.config.get("duid", ""))
            subnet_cidr = str(resource.config.get("subnet", ""))
            subnet_uuid = _resolve_subnet_uuid(cidr_to_uuid, subnet_cidr, resource.name)
            uuid = live_by_key.get((duid, subnet_uuid))
            if not uuid:
                continue
            service.delete_dhcpv6_reservation(uuid)
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
        """Return ``{resource_name: opnsense_uuid}`` for live reservations.

        Matches by the natural-key ``(duid, subnet_uuid)`` tuple. The
        operator-facing ``name`` is only used as the dict key in the
        return value.

        Args:
            env_name: Active environment name.
            resources: DHCPv6 reservation ``ResourceConfig`` entries.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            Mapping from operator-facing resource name to OPNsense UUID.
            Resources without a matching live record are omitted.

        Raises:
            ReferenceValidationError: If any reservation references a
                ``subnet`` CIDR that does not match any live DHCPv6 subnet.
        """
        service = KeaDHCPService.from_environment(env_name, provider_name, self.config_dir)
        cidr_to_uuid = _build_subnet_cidr_lookup(service)

        live_reservations = service.search_dhcpv6_reservations()
        live_by_key: dict[tuple[str, str], str] = {
            (str(r.get("duid", "")), str(r.get("subnet", ""))): str(r.get("uuid", ""))
            for r in live_reservations
        }

        result: dict[str, str] = {}
        for resource in resources:
            duid = str(resource.config.get("duid", ""))
            subnet_cidr = str(resource.config.get("subnet", ""))
            subnet_uuid = _resolve_subnet_uuid(cidr_to_uuid, subnet_cidr, resource.name)
            uuid = live_by_key.get((duid, subnet_uuid))
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

        Resolves each reservation's ``subnet`` CIDR to a live subnet
        UUID via ``search_dhcpv6_subnets``; raises
        ``ReferenceValidationError`` if the CIDR doesn't match any live
        subnet (a deliberate upgrade over today's silent-skip path).
        """
        cidr_to_uuid = _build_subnet_cidr_lookup(service)

        live_reservations = service.search_dhcpv6_reservations()
        live_by_key: dict[tuple[str, str], dict[str, Any]] = {
            (str(r.get("duid", "")), str(r.get("subnet", ""))): r for r in live_reservations
        }

        adds: list[dict[str, Any]] = []
        updates: list[tuple[str, dict[str, Any]]] = []
        seen_keys: set[tuple[str, str]] = set()

        for resource in resources:
            subnet_cidr = str(resource.config.get("subnet", ""))
            subnet_uuid = _resolve_subnet_uuid(cidr_to_uuid, subnet_cidr, resource.name)
            reservation_data = _build_reservation_payload(resource, subnet_uuid)
            duid = str(reservation_data["duid"])
            key = (duid, subnet_uuid)
            seen_keys.add(key)

            existing = live_by_key.get(key)
            if existing is not None:
                existing_uuid = str(existing.get("uuid", ""))
                current = service.get_dhcpv6_reservation(existing_uuid)
                current_fields = _extract_reservation_fields(current)
                desired_fields = _build_desired_reservation_fields(reservation_data)
                if current_fields != desired_fields:
                    _log_field_diff(
                        f"DHCPv6 reservation {resource.name}",
                        current_fields,
                        desired_fields,
                    )
                    updates.append(
                        (existing_uuid, {**reservation_data, "__name__": resource.name}),
                    )
            else:
                adds.append({**reservation_data, "__name__": resource.name})

        deletes: list[tuple[str, str]] = []
        if not add_only:
            for (duid, subnet_uuid), live in live_by_key.items():
                if (duid, subnet_uuid) in seen_keys:
                    continue
                live_uuid = str(live.get("uuid", ""))
                if not live_uuid:
                    continue
                # Synthetic descriptor for the delete outcome's resource_name.
                descriptor = duid or live_uuid
                deletes.append((live_uuid, descriptor))

        return _Diff(adds=adds, updates=updates, deletes=deletes)


def _build_subnet_cidr_lookup(service: KeaDHCPService) -> dict[str, str]:
    """Build a ``{subnet_cidr: subnet_uuid}`` map from live DHCPv6 subnets.

    Mirrors :func:`unbound_host_alias._resolve_host_uuids` — one search
    call, build a name-shaped lookup, fail loudly on misses at the call
    site.

    Args:
        service: ``KeaDHCPService`` already bound to the active env.

    Returns:
        Map from each live subnet's CIDR to its UUID.
    """
    rows = service.search_dhcpv6_subnets()
    lookup: dict[str, str] = {}
    for row in rows:
        cidr = str(row.get("subnet", ""))
        uuid = str(row.get("uuid", ""))
        if cidr and uuid:
            lookup[cidr] = uuid
    return lookup


def _resolve_subnet_uuid(
    cidr_to_uuid: dict[str, str],
    subnet_cidr: str,
    resource_name: str,
) -> str:
    """Resolve a reservation's ``subnet`` CIDR to a live subnet UUID.

    Args:
        cidr_to_uuid: Pre-built map from CIDR to UUID.
        subnet_cidr: Operator-facing subnet reference (e.g., ``fd00:1::/64``).
        resource_name: Operator-facing reservation name for error messages.

    Returns:
        Live OPNsense subnet UUID.

    Raises:
        ReferenceValidationError: If ``subnet_cidr`` does not match any
            live DHCPv6 subnet on the box. This is a behavioral upgrade
            over the legacy ``_generate_kea_dhcp6_resources`` path,
            which silently skipped reservations with unresolved subnets.
    """
    uuid = cidr_to_uuid.get(subnet_cidr)
    if not uuid:
        raise ReferenceValidationError(
            f"kea_dhcp6_reservation '{resource_name}' references unknown "
            f"subnet '{subnet_cidr}'; no live kea_dhcp6_subnet matches"
        )
    return uuid


def _build_reservation_payload(resource: ResourceConfig, subnet_uuid: str) -> dict[str, Any]:
    """Build the wire-format payload sent to OPNsense for a reservation.

    Mirrors the original ``_generate_kea_dhcp6_resources`` construction
    shape so wire-level behavior is unchanged.

    Args:
        resource: DHCPv6 reservation resource.
        subnet_uuid: Resolved subnet UUID (populated by the caller).

    Returns:
        Dict suitable for passing to ``service.add_dhcpv6_reservation`` /
        ``service.update_dhcpv6_reservation``.
    """
    config = resource.config
    return {
        "subnet": subnet_uuid,
        "ip_address": config.get("ip_address"),
        "duid": config.get("duid"),
        "hostname": config.get("hostname", ""),
        "description": config.get("description", ""),
    }
