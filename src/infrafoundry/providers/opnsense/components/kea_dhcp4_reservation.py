"""Kea DHCPv4 reservation component manager for OPNsense (ADR-0014, #778).

Implements the standard ``plan`` / ``apply`` / ``destroy`` /
``get_resource_ids`` surface against ``KeaDHCPService`` so that
``OPNsenseDirectRunner`` can dispatch DHCPv4 reservations alongside the
other direct-API components. Replaces the terraform write path
(``opnsense_kea_reservation`` via ``browningluke/opnsense``) that
previously ran under ``generate_terraform()``.

Mirrors :mod:`.kea_dhcp6_reservation` line-for-line; differences are
flagged inline:

- Identity is the natural key ``(hw_address, subnet_uuid)`` — DHCPv4
  uses MAC address, not DUID. ``subnet_uuid`` is resolved at apply time
  by reading ``service.search_dhcpv4_subnets()`` and matching the
  operator-facing subnet CIDR to the live subnet UUID. If no live subnet
  matches, the manager raises :class:`ReferenceValidationError` so the
  failure surfaces at plan time rather than as a silent skip-with-warning
  at apply time.
- Wire schema: ``subnet`` (UUID on the wire; see operator-facing schema
  below), ``hw_address`` (MAC), ``ip_address``, ``hostname``,
  ``description``.

Operator-facing schema (#802):

- Preferred: ``subnet_ref: <managed kea.dhcp4.subnets name>`` — what the
  framework's blueprints emit. Resolved against the sibling
  ``kea.dhcp4.subnets`` resource list to yield the CIDR, then through
  the live ``search_dhcpv4_subnets`` lookup to yield the wire-format
  UUID.
- Legacy: ``subnet: <CIDR>`` — direct CIDR literal; still supported.
- Both fields present must agree on the resolved CIDR; mismatch raises
  :class:`ReferenceValidationError`.
- Both fields absent raises :class:`ReferenceValidationError`.

The sibling ``kea.dhcp4.subnets`` resource slice is threaded into each
public method by ``OPNsenseDirectRunner`` via the
``sibling_resources`` kwarg, gated on the
``SIBLING_RESOURCE_TYPE`` ClassVar marker.

Reconfigure semantics:

- This manager **does not** call ``service.reconfigure()`` directly.
  It declares ``FINALIZATION_HOOK = "kea_reconfigure"`` (the same key
  as :class:`KeaDHCPv4SubnetManager` and the DHCPv6 managers) so the
  runner fires exactly one Kea reconfigure even when both subnets and
  reservations changed in the same apply.
"""

from __future__ import annotations

from typing import Any, ClassVar

from infrafoundry.core.exceptions import ReferenceValidationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..services.kea_dhcp import (
    KeaDHCPService,
    _build_desired_reservation4_fields,
    _extract_reservation4_fields,
    _log_field_diff,
)
from .base import BaseComponentManager


class _Diff:
    """Add/update/delete plan for DHCPv4 reservations.

    Same shape as :class:`.kea_dhcp4_subnet._Diff` so the runner's
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


class KeaDHCPv4ReservationManager(BaseComponentManager):
    """Manager for OPNsense Kea DHCPv4 reservation operations."""

    #: Runner-level finalization hook key. Matched against
    #: ``OPNsenseProvider.get_finalization_hooks()``; shared with
    #: :class:`KeaDHCPv4SubnetManager` and the DHCPv6 managers so a
    #: single Kea reconfigure fires per apply when any Kea-managed
    #: component changed state.
    FINALIZATION_HOOK: ClassVar[str] = "kea_reconfigure"

    #: Resource type whose ``ResourceConfig`` slice the runner threads
    #: into each public method as the ``sibling_resources`` kwarg (#802).
    #: The slice is consumed by ``_build_subnet_name_to_cidr`` to resolve
    #: ``subnet_ref`` to a CIDR before the live UUID lookup.
    SIBLING_RESOURCE_TYPE: ClassVar[str | None] = "kea.dhcp4.subnets"

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
        sibling_resources: list[ResourceConfig] | None = None,
    ) -> _Diff:
        """Compute the add/update/delete diff for the given reservations.

        Args:
            env_name: Active environment name.
            resources: DHCPv4 reservation ``ResourceConfig`` entries.
            add_only: If True, suppress deletes for live reservations not in YAML.
            provider_name: Provider identifier (defaults to ``opnsense``).
            sibling_resources: ``kea.dhcp4.subnets`` resources, threaded
                in by ``OPNsenseDirectRunner``. Used to resolve
                ``subnet_ref`` to a CIDR (#802). ``None`` (or empty) is
                fine for resources using the legacy ``subnet: <CIDR>``
                form exclusively.

        Returns:
            ``_Diff`` describing what apply would do.

        Raises:
            ReferenceValidationError: If any reservation's ``subnet_ref``
                or ``subnet`` CIDR does not match any live DHCPv4 subnet,
                or if both fields disagree, or if neither is present.
        """
        service = KeaDHCPService.from_environment(env_name, provider_name, self.config_dir)
        name_to_cidr = _build_subnet_name_to_cidr(sibling_resources)
        return self._compute_diff(service, resources, add_only=add_only, name_to_cidr=name_to_cidr)

    def apply(
        self,
        env_name: str,
        resources: list[ResourceConfig],
        *,
        auto_approve: bool = True,
        add_only: bool = False,
        provider_name: str = "opnsense",
        sibling_resources: list[ResourceConfig] | None = None,
    ) -> dict[str, Any]:
        """Apply the diff: add / update / delete DHCPv4 reservations.

        Does **not** call ``service.reconfigure()`` directly — see the
        module docstring for the runner-side hook contract.

        Args:
            env_name: Active environment name.
            resources: DHCPv4 reservation ``ResourceConfig`` entries.
            auto_approve: Currently a no-op; the diff engine is the gate.
            add_only: If True, suppress deletes.
            provider_name: Provider identifier (defaults to ``opnsense``).
            sibling_resources: ``kea.dhcp4.subnets`` resources, threaded
                in by ``OPNsenseDirectRunner``. Used to resolve
                ``subnet_ref`` to a CIDR (#802).

        Returns:
            Dict with ``resources_created``, ``resources_updated``,
            ``resources_deleted`` counts and a ``resource_outcomes`` list.

        Raises:
            ReferenceValidationError: If any reservation's ``subnet_ref``
                or ``subnet`` CIDR does not match any live DHCPv4 subnet,
                or if both fields disagree, or if neither is present.
        """
        del auto_approve
        service = KeaDHCPService.from_environment(env_name, provider_name, self.config_dir)
        name_to_cidr = _build_subnet_name_to_cidr(sibling_resources)
        diff = self._compute_diff(service, resources, add_only=add_only, name_to_cidr=name_to_cidr)

        outcomes: list[ResourceOutcome] = []
        created = 0
        updated = 0
        deleted = 0

        for reservation_data in diff.adds:
            reservation_name = str(reservation_data.pop("__name__"))
            result = service.add_dhcpv4_reservation(reservation_data)
            if result.get("result") == "failed":
                validations = result.get("validations", {})
                raise ValueError(
                    f"Failed to create DHCPv4 reservation {reservation_name}: {validations}"
                )
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_kea_reservation.{reservation_name}",
                    action="add",
                    resource_name=reservation_name,
                )
            )
            created += 1

        for uuid, reservation_data in diff.updates:
            reservation_name = str(reservation_data.pop("__name__"))
            service.update_dhcpv4_reservation(uuid, reservation_data)
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_kea_reservation.{reservation_name}",
                    action="update",
                    resource_name=reservation_name,
                )
            )
            updated += 1

        for uuid, descriptor in diff.deletes:
            service.delete_dhcpv4_reservation(uuid)
            synthetic_name = f"reservation-{descriptor}"
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_kea_reservation.{synthetic_name}",
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
        sibling_resources: list[ResourceConfig] | None = None,
    ) -> dict[str, Any]:
        """Delete every live reservation matching ``resources``.

        Matches by ``(hw_address, subnet_uuid)`` — the natural-key tuple.
        The ``subnet_uuid`` is resolved from each resource's ``subnet``
        CIDR via ``search_dhcpv4_subnets`` (mirrors apply-time resolution).

        Args:
            env_name: Active environment name.
            resources: DHCPv4 reservation ``ResourceConfig`` entries to destroy.
            auto_approve: Currently a no-op.
            provider_name: Provider identifier (defaults to ``opnsense``).
            sibling_resources: ``kea.dhcp4.subnets`` resources, threaded
                in by ``OPNsenseDirectRunner``. Used to resolve
                ``subnet_ref`` to a CIDR (#802).

        Returns:
            Dict with ``resources_destroyed`` and ``locked_skipped`` counts.

        Raises:
            ReferenceValidationError: If any reservation's ``subnet_ref``
                or ``subnet`` CIDR does not match any live DHCPv4 subnet,
                or if both fields disagree, or if neither is present.
        """
        del auto_approve
        service = KeaDHCPService.from_environment(env_name, provider_name, self.config_dir)
        name_to_cidr = _build_subnet_name_to_cidr(sibling_resources)
        cidr_to_uuid = _build_subnet_cidr_lookup(service)

        live_reservations = service.search_dhcpv4_reservations()
        live_by_key: dict[tuple[str, str], str] = {
            (str(r.get("hw_address", "")), str(r.get("subnet", ""))): str(r.get("uuid", ""))
            for r in live_reservations
        }

        deleted = 0
        for resource in resources:
            hw_address = str(resource.config.get("hw_address", ""))
            subnet_cidr = _resolve_subnet_cidr(resource, name_to_cidr)
            subnet_uuid = _resolve_subnet_uuid(cidr_to_uuid, subnet_cidr, resource.name)
            uuid = live_by_key.get((hw_address, subnet_uuid))
            if not uuid:
                continue
            service.delete_dhcpv4_reservation(uuid)
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
        sibling_resources: list[ResourceConfig] | None = None,
    ) -> dict[str, str]:
        """Return ``{resource_name: opnsense_uuid}`` for live reservations.

        Matches by the natural-key ``(hw_address, subnet_uuid)`` tuple. The
        operator-facing ``name`` is only used as the dict key in the
        return value.

        Args:
            env_name: Active environment name.
            resources: DHCPv4 reservation ``ResourceConfig`` entries.
            provider_name: Provider identifier (defaults to ``opnsense``).
            sibling_resources: ``kea.dhcp4.subnets`` resources, threaded
                in by ``OPNsenseDirectRunner``. Used to resolve
                ``subnet_ref`` to a CIDR (#802).

        Returns:
            Mapping from operator-facing resource name to OPNsense UUID.
            Resources without a matching live record are omitted.

        Raises:
            ReferenceValidationError: If any reservation's ``subnet_ref``
                or ``subnet`` CIDR does not match any live DHCPv4 subnet,
                or if both fields disagree, or if neither is present.
        """
        service = KeaDHCPService.from_environment(env_name, provider_name, self.config_dir)
        name_to_cidr = _build_subnet_name_to_cidr(sibling_resources)
        cidr_to_uuid = _build_subnet_cidr_lookup(service)

        live_reservations = service.search_dhcpv4_reservations()
        live_by_key: dict[tuple[str, str], str] = {
            (str(r.get("hw_address", "")), str(r.get("subnet", ""))): str(r.get("uuid", ""))
            for r in live_reservations
        }

        result: dict[str, str] = {}
        for resource in resources:
            hw_address = str(resource.config.get("hw_address", ""))
            subnet_cidr = _resolve_subnet_cidr(resource, name_to_cidr)
            subnet_uuid = _resolve_subnet_uuid(cidr_to_uuid, subnet_cidr, resource.name)
            uuid = live_by_key.get((hw_address, subnet_uuid))
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
        name_to_cidr: dict[str, str],
    ) -> _Diff:
        """Compute the add/update/delete diff against live state.

        Resolves each reservation's ``subnet_ref`` (or legacy ``subnet``)
        to a CIDR via the sibling-resource map, then to a live subnet
        UUID via ``search_dhcpv4_subnets``; raises
        ``ReferenceValidationError`` on any miss (mirrors the DHCPv6
        manager's behavior).
        """
        cidr_to_uuid = _build_subnet_cidr_lookup(service)

        live_reservations = service.search_dhcpv4_reservations()
        live_by_key: dict[tuple[str, str], dict[str, Any]] = {
            (str(r.get("hw_address", "")), str(r.get("subnet", ""))): r for r in live_reservations
        }

        adds: list[dict[str, Any]] = []
        updates: list[tuple[str, dict[str, Any]]] = []
        seen_keys: set[tuple[str, str]] = set()

        for resource in resources:
            subnet_cidr = _resolve_subnet_cidr(resource, name_to_cidr)
            subnet_uuid = _resolve_subnet_uuid(cidr_to_uuid, subnet_cidr, resource.name)
            reservation_data = _build_reservation_payload(resource, subnet_uuid)
            hw_address = str(reservation_data["hw_address"])
            key = (hw_address, subnet_uuid)
            seen_keys.add(key)

            existing = live_by_key.get(key)
            if existing is not None:
                existing_uuid = str(existing.get("uuid", ""))
                current = service.get_dhcpv4_reservation(existing_uuid)
                current_fields = _extract_reservation4_fields(current)
                desired_fields = _build_desired_reservation4_fields(reservation_data)
                if current_fields != desired_fields:
                    _log_field_diff(
                        f"DHCPv4 reservation {resource.name}",
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
            for (hw_address, subnet_uuid), live in live_by_key.items():
                if (hw_address, subnet_uuid) in seen_keys:
                    continue
                live_uuid = str(live.get("uuid", ""))
                if not live_uuid:
                    continue
                # Synthetic descriptor for the delete outcome's resource_name.
                descriptor = hw_address or live_uuid
                deletes.append((live_uuid, descriptor))

        return _Diff(adds=adds, updates=updates, deletes=deletes)


def _build_subnet_cidr_lookup(service: KeaDHCPService) -> dict[str, str]:
    """Build a ``{subnet_cidr: subnet_uuid}`` map from live DHCPv4 subnets.

    Mirrors :func:`.kea_dhcp6_reservation._build_subnet_cidr_lookup` —
    one search call, build a name-shaped lookup, fail loudly on misses
    at the call site.

    Args:
        service: ``KeaDHCPService`` already bound to the active env.

    Returns:
        Map from each live subnet's CIDR to its UUID.
    """
    rows = service.search_dhcpv4_subnets()
    lookup: dict[str, str] = {}
    for row in rows:
        cidr = str(row.get("subnet", ""))
        uuid = str(row.get("uuid", ""))
        if cidr and uuid:
            lookup[cidr] = uuid
    return lookup


def _build_subnet_name_to_cidr(
    sibling_resources: list[ResourceConfig] | None,
) -> dict[str, str]:
    """Build a ``{subnet_name: subnet_cidr}`` map from sibling subnet resources (#802).

    The runner threads the ``kea.dhcp4.subnets`` slice in via the
    ``sibling_resources`` kwarg on each public method; this helper turns
    it into the name→CIDR map used by ``_resolve_subnet_cidr``. Subnets
    missing or with non-string ``subnet`` fields are skipped — those
    will surface as malformed-config errors elsewhere in the pipeline.

    Args:
        sibling_resources: ``kea.dhcp4.subnets`` resources, or ``None``
            (treated as empty).

    Returns:
        Map from operator-facing subnet name to CIDR; empty if the
        sibling slice is None / empty.
    """
    if not sibling_resources:
        return {}
    name_to_cidr: dict[str, str] = {}
    for subnet in sibling_resources:
        cidr = subnet.config.get("subnet")
        if isinstance(cidr, str) and cidr:
            name_to_cidr[subnet.name] = cidr
    return name_to_cidr


def _resolve_subnet_cidr(
    resource: ResourceConfig,
    name_to_cidr: dict[str, str],
) -> str:
    """Resolve a reservation's operator-facing subnet field to a CIDR (#802).

    Field acceptance precedence (matches
    ``KeaReservationValidator._validate_one``):

    1. ``subnet_ref`` present → resolve via ``name_to_cidr``; raise
       ``ReferenceValidationError`` if it doesn't resolve.
    2. Only ``subnet`` present → use directly (back-compat).
    3. Both present and agree → use the resolved CIDR.
    4. Both present and disagree → ``ReferenceValidationError``.
    5. Neither present → ``ReferenceValidationError``.

    Args:
        resource: DHCPv4 reservation resource.
        name_to_cidr: Map from sibling subnet names to their CIDRs (built
            once by ``_build_subnet_name_to_cidr``).

    Returns:
        The resolved subnet CIDR string.

    Raises:
        ReferenceValidationError: When the reservation lacks both fields,
            when both fields disagree, or when ``subnet_ref`` does not
            resolve to a managed sibling subnet.
    """
    subnet_ref = resource.config.get("subnet_ref")
    subnet_literal = resource.config.get("subnet")

    if subnet_ref is None and subnet_literal is None:
        raise ReferenceValidationError(
            f"kea_reservation '{resource.name}' missing required field; "
            f"expected one of 'subnet_ref' (preferred) or 'subnet' (legacy CIDR)"
        )

    resolved: str | None = None
    if subnet_ref is not None:
        if not isinstance(subnet_ref, str) or not subnet_ref:
            raise ReferenceValidationError(
                f"kea_reservation '{resource.name}' subnet_ref must be a non-empty string"
            )
        # Accept fully qualified dotted forms like
        # ``kea.dhcp4.subnets.<name>`` by taking the trailing segment.
        candidate = subnet_ref.split(".")[-1] if "." in subnet_ref else subnet_ref
        resolved = name_to_cidr.get(candidate)
        if resolved is None:
            raise ReferenceValidationError(
                f"kea_reservation '{resource.name}' references unknown "
                f"subnet_ref '{subnet_ref}'; no managed kea.dhcp4.subnets resource matches"
            )

    if subnet_literal is not None and resolved is not None:
        literal_str = str(subnet_literal)
        if literal_str != resolved:
            raise ReferenceValidationError(
                f"kea_reservation '{resource.name}' has conflicting subnet fields: "
                f"subnet_ref={subnet_ref!r} resolves to {resolved!r}, "
                f"but subnet={literal_str!r}"
            )
        return resolved

    if resolved is not None:
        return resolved

    return str(subnet_literal)


def _resolve_subnet_uuid(
    cidr_to_uuid: dict[str, str],
    subnet_cidr: str,
    resource_name: str,
) -> str:
    """Resolve a reservation's ``subnet`` CIDR to a live subnet UUID.

    Args:
        cidr_to_uuid: Pre-built map from CIDR to UUID.
        subnet_cidr: Operator-facing subnet reference (e.g., ``192.168.1.0/24``).
        resource_name: Operator-facing reservation name for error messages.

    Returns:
        Live OPNsense subnet UUID.

    Raises:
        ReferenceValidationError: If ``subnet_cidr`` does not match any
            live DHCPv4 subnet on the box. This is a behavioral upgrade
            over the legacy terraform path, which silently failed when
            the subnet didn't exist (terraform-graph dependency would be
            broken by the box-to-box cutover).
    """
    uuid = cidr_to_uuid.get(subnet_cidr)
    if not uuid:
        raise ReferenceValidationError(
            f"kea_reservation '{resource_name}' references unknown "
            f"subnet '{subnet_cidr}'; no live kea_subnet matches"
        )
    return uuid


def _build_reservation_payload(resource: ResourceConfig, subnet_uuid: str) -> dict[str, Any]:
    """Build the wire-format payload sent to OPNsense for a DHCPv4 reservation.

    Mirrors the legacy terraform template (``kea_reservation.tf.j2``)
    field coverage so wire-level behavior is unchanged. DHCPv4 uses
    ``hw_address`` (MAC) for client identity, distinct from DHCPv6's
    ``duid``.

    Args:
        resource: DHCPv4 reservation resource.
        subnet_uuid: Resolved subnet UUID (populated by the caller).

    Returns:
        Dict suitable for passing to ``service.add_dhcpv4_reservation`` /
        ``service.update_dhcpv4_reservation``.
    """
    config = resource.config
    return {
        "subnet": subnet_uuid,
        "hw_address": config.get("hw_address"),
        "ip_address": config.get("ip_address"),
        "hostname": config.get("hostname", resource.name),
        "description": config.get("description", ""),
    }
