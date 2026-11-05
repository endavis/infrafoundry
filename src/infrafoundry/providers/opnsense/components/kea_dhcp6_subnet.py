"""Kea DHCPv6 subnet component manager for OPNsense (ADR-0014, #758).

Implements the standard ``plan`` / ``apply`` / ``destroy`` / ``get_resource_ids``
surface against ``KeaDHCPService`` so that ``OPNsenseDirectRunner`` can dispatch
DHCPv6 subnets alongside the other direct-API components. Replaces the inline
``OPNsenseProvider._generate_kea_dhcp6_resources`` path that previously ran
under ``generate_terraform()`` (#758).

The change-detection helpers used here live at module scope in
``services/kea_dhcp.py`` (relocated in #758, byte-identical move so the
asymmetric ``valid_lifetime`` and option-dict normalization fixes from PR
#757 / #756 survive intact).

Identity / wire schema:

- Identity is the natural key ``subnet`` (the IPv6 CIDR string, e.g.,
  ``fd00:1::/64``). Matches the original ``_generate_kea_dhcp6_resources``
  implementation.
- Wire schema: ``subnet``, ``interface``, ``pools`` (newline-joined
  ``range`` strings), ``valid_lifetime`` (string), ``description``,
  and ``option_data`` (with ``dns_servers`` / ``domain_search`` as
  comma-joined strings) — same shape ``KeaClient.add_dhcp6_subnet`` and
  ``update_dhcp6_subnet`` accept.
- The ``add`` API response does not include the new UUID; the manager
  re-runs ``search_dhcpv6_subnets`` after each create to recover it.

Reconfigure semantics:

- This manager **does not** call ``service.reconfigure()`` directly.
  Instead it declares ``FINALIZATION_HOOK = "kea_reconfigure"`` and
  ``OPNsenseDirectRunner`` fires the matching hook from
  ``OPNsenseProvider.get_finalization_hooks()`` exactly once after the
  apply loop, so DHCPv4 + DHCPv6 subnets and reservations share a
  single Kea reconfigure (preserving today's "one reconfigure per
  plan/apply" operational behavior). The hook key was renamed from
  ``kea_dhcp6_reconfigure`` (#758) to ``kea_reconfigure`` in #777/#778
  when DHCPv4 was migrated to direct-API and joined the same hook.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import ResourceOutcome

from ..services.kea_dhcp import (
    KeaDHCPService,
    _build_desired_subnet_fields,
    _drop_non_round_trip_subnet_fields,
    _extract_subnet_fields,
    _log_field_diff,
)
from ._kea_blockers import live_reservations_by_subnet, split_blocked_deletes
from ._managed import subnet_cidr_keys
from .base import BaseComponentManager
from .kea_dhcp6_reservation import _build_subnet_name_to_cidr, reservations_kept_on_subnets

logger = logging.getLogger(__name__)


class _Diff:
    """Add/update/delete plan for DHCPv6 subnets.

    Lightweight container shaped after the other direct-API services'
    ``Diff`` dataclasses so the runner's ``_format_plan_summary`` can
    read ``adds``/``updates``/``deletes``/``locked`` and ``is_empty``
    uniformly. ``unmanaged`` holds live subnets kept because InfraFoundry never
    applied them (ADR-0018). ``locked`` is always empty here — DHCPv6 subnets do not
    yet support the per-resource ``lock: true`` annotation; promoting
    it is a separate change.
    """

    def __init__(
        self,
        *,
        adds: list[dict[str, Any]] | None = None,
        updates: list[tuple[str, dict[str, Any]]] | None = None,
        deletes: list[tuple[str, str]] | None = None,
        unmanaged: list[tuple[str, str]] | None = None,
        blocked: list[tuple[str, str, list[str]]] | None = None,
        warnings: list[str] | None = None,
    ) -> None:
        self.adds: list[dict[str, Any]] = adds or []
        self.updates: list[tuple[str, dict[str, Any]]] = updates or []
        self.deletes: list[tuple[str, str]] = deletes or []
        self.unmanaged: list[tuple[str, str]] = unmanaged or []
        # Deletes refused because reservations InfraFoundry does not manage still use the
        # subnet: (uuid, cidr, descriptors). ``is_empty`` ignores them (#1264).
        self.blocked: list[tuple[str, str, list[str]]] = blocked or []
        self.warnings: list[str] = warnings or []
        self.locked: list[Any] = []

    @property
    def is_empty(self) -> bool:
        """Return True when there are no add/update/delete operations to apply."""
        return not (self.adds or self.updates or self.deletes)


class KeaDHCPv6SubnetManager(BaseComponentManager):
    """Manager for OPNsense Kea DHCPv6 subnet operations.

    Plan/apply/destroy delegate to ``KeaDHCPService``; the runner is
    responsible for translating exceptions into ``PlanResult.error`` /
    ``ApplyResult.error``. Reconfigure is deferred to the runner's
    finalization-hook plumbing — see module docstring.
    """

    #: Runner-level finalization hook key. Matched against the keys
    #: returned by ``OPNsenseProvider.get_finalization_hooks()``; the
    #: reservation manager declares the same value, and so do the
    #: DHCPv4 managers (#777, #778), so a single Kea reconfigure fires
    #: per apply when any Kea component changed state.
    FINALIZATION_HOOK: ClassVar[str] = "kea_reconfigure"

    #: Deletes are limited to the rows InfraFoundry applied before (ADR-0018).
    DELETE_SCOPE: ClassVar[str] = "managed_set"

    #: The runner deletes in a separate phase after the reservation manager, so a
    #: subnet is deleted only once its reservations are gone (#1264).
    SPLIT_DELETE_PHASE: ClassVar[bool] = True

    #: Resource type whose YAML and managed rows the runner threads in as
    #: ``dependent_resources`` / ``managed_dependent_resources``, to predict which
    #: subnet deletes would orphan a reservation (#1264).
    DEPENDENT_RESOURCE_TYPE: ClassVar[str | None] = "kea.dhcp6.reservations"

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
        dependent_resources: list[ResourceConfig] | None = None,
        managed_dependent_resources: list[ResourceConfig] | None = None,
        provider_name: str = "opnsense",
    ) -> _Diff:
        """Compute the add/update/delete diff for the given subnets.

        Args:
            env_name: Active environment name.
            resources: DHCPv6 subnet ``ResourceConfig`` entries (filtered upstream).
            add_only: If True, suppress deletes for live subnets not in YAML.
            managed_resources: Rows InfraFoundry applied before (ADR-0018). When given,
                only live subnets matching them may be deleted; ``None`` deletes every
                live subnet missing from YAML.
            dependent_resources: ``kea.dhcp6.reservations`` in YAML, used to predict which
                subnet deletes a reservation would block (#1264).
            managed_dependent_resources: Managed reservation rows, as for ``managed_resources``.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            ``_Diff`` describing what apply would do.
        """
        service = KeaDHCPService.from_environment(env_name, provider_name, self.config_dir)
        return self._compute_diff(
            service,
            resources,
            add_only=add_only,
            managed_keys=subnet_cidr_keys(managed_resources),
            managed_subnets=managed_resources,
            dependent_resources=dependent_resources,
            managed_dependent_resources=managed_dependent_resources,
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
        dependent_resources: list[ResourceConfig] | None = None,
        managed_dependent_resources: list[ResourceConfig] | None = None,
        provider_name: str = "opnsense",
    ) -> dict[str, Any]:
        """Apply the diff: add / update / delete DHCPv6 subnets.

        Does **not** call ``service.reconfigure()`` directly — the runner
        fires the ``kea_reconfigure`` finalization hook once after every
        component has applied. This preserves today's "one reconfigure
        per plan/apply" operational behavior across all four Kea
        managers (DHCPv4 + DHCPv6, subnet + reservation).

        Args:
            env_name: Active environment name.
            resources: DHCPv6 subnet ``ResourceConfig`` entries.
            auto_approve: Currently a no-op; the diff engine is the gate.
            add_only: If True, suppress deletes.
            deletes_only: If True, only delete: the runner's delete phase, run after the
                reservation manager deleted its reservations (#1264). Any reservation
                still on a subnet then blocks its delete.
            managed_resources: Rows InfraFoundry applied before (ADR-0018). When given,
                only live subnets matching them may be deleted; ``None`` deletes every
                live subnet missing from YAML.
            dependent_resources: ``kea.dhcp6.reservations`` in YAML, used to predict which
                subnet deletes a reservation would block (#1264).
            managed_dependent_resources: Managed reservation rows, as for ``managed_resources``.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            Dict with ``resources_created``, ``resources_updated``,
            ``resources_deleted`` counts and a ``resource_outcomes`` list.
        """
        del auto_approve  # diff engine is the gate; flag accepted for protocol shape
        service = KeaDHCPService.from_environment(env_name, provider_name, self.config_dir)

        # Ensure DHCPv6 service is enabled with the required interfaces before
        # we mutate subnets — preserves the legacy provider behavior
        # (``_generate_kea_dhcp6_resources`` did this unconditionally).
        required_interfaces = sorted(
            {str(r.config.get("interface")) for r in resources if r.config.get("interface")}
        )
        if required_interfaces and not deletes_only:
            service.ensure_dhcpv6_enabled(required_interfaces)

        unresolved_managed: set[str] = set()
        diff = self._compute_diff(
            service,
            resources,
            add_only=add_only,
            managed_keys=subnet_cidr_keys(managed_resources, unresolved_managed),
            managed_subnets=managed_resources,
            dependent_resources=dependent_resources,
            managed_dependent_resources=managed_dependent_resources,
            deletes_only=deletes_only,
        )
        for _, blocked_cidr, _ in diff.blocked:
            # Keep the row managed so the next run retries the delete and warns again.
            unresolved_managed.update(
                row.name
                for row in managed_resources or []
                if str(row.config.get("subnet", "")) == blocked_cidr
            )
        for warning in diff.warnings:
            logger.warning("kea subnet: %s", warning)

        outcomes: list[ResourceOutcome] = []
        created = 0
        updated = 0
        deleted = 0

        for subnet_data in diff.adds:
            subnet_name = str(subnet_data.pop("__name__"))
            subnet_address = str(subnet_data.get("subnet", ""))
            result = service.add_dhcpv6_subnet(subnet_data)
            if result.get("result") == "failed":
                raise ValueError(f"Failed to create DHCPv6 subnet {subnet_name}: {result}")
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_kea_dhcp6_subnet.{subnet_name}",
                    action="add",
                    resource_name=subnet_name,
                )
            )
            created += 1
            del subnet_address  # informational only

        for uuid, subnet_data in diff.updates:
            subnet_name = str(subnet_data.pop("__name__"))
            service.update_dhcpv6_subnet(uuid, subnet_data)
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_kea_dhcp6_subnet.{subnet_name}",
                    action="update",
                    resource_name=subnet_name,
                )
            )
            updated += 1

        for uuid, subnet_address in diff.deletes:
            service.delete_dhcpv6_subnet(uuid)
            synthetic_name = f"subnet-{subnet_address}"
            outcomes.append(
                ResourceOutcome(
                    address=f"opnsense_kea_dhcp6_subnet.{synthetic_name}",
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
            "unresolved_managed": sorted(unresolved_managed),
            "warnings": list(diff.warnings),
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

        DHCPv6 subnets do not yet honor a per-resource ``lock`` flag at
        the diff layer; ``locked_skipped`` is always 0 today. Adding
        ``lock`` support is a separate change.

        Args:
            env_name: Active environment name.
            resources: DHCPv6 subnet ``ResourceConfig`` entries to destroy.
            auto_approve: Currently a no-op.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            Dict with ``resources_destroyed`` and ``locked_skipped`` counts.
        """
        del auto_approve
        service = KeaDHCPService.from_environment(env_name, provider_name, self.config_dir)

        existing = service.search_dhcpv6_subnets()
        existing_by_subnet = {str(s.get("subnet", "")): str(s.get("uuid", "")) for s in existing}

        deleted = 0
        candidates = [
            (existing_by_subnet[addr], addr)
            for addr in (str(r.config.get("subnet", "")) for r in resources)
            if existing_by_subnet.get(addr)
        ]
        # The reservation destroy ran first; refuse any subnet that still has reservations.
        still_used = live_reservations_by_subnet(
            service.search_dhcpv6_reservations(), {u for u, _ in candidates}, "duid"
        )
        _, blocked, warnings = split_blocked_deletes(candidates, still_used, "kea.dhcp6.subnets")
        blocked_uuids = {uuid for uuid, _, _ in blocked}
        for warning in warnings:
            logger.warning("kea subnet: %s", warning)
        for resource in resources:
            subnet_address = str(resource.config.get("subnet", ""))
            uuid = existing_by_subnet.get(subnet_address)
            if not uuid or uuid in blocked_uuids:
                continue
            service.delete_dhcpv6_subnet(uuid)
            deleted += 1

        return {
            "success": True,
            "resources_destroyed": deleted,
            "locked_skipped": 0,
            "blocked_skipped": len(blocked),
            "warnings": warnings,
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
        """Return ``{resource_name: opnsense_uuid}`` for live DHCPv6 subnets.

        Matches by the natural-key ``subnet`` CIDR; the operator-facing
        ``name`` is only used as the dict key in the return value.

        Args:
            env_name: Active environment name.
            resources: DHCPv6 subnet ``ResourceConfig`` entries.
            provider_name: Provider identifier (defaults to ``opnsense``).

        Returns:
            Mapping from operator-facing resource name to OPNsense UUID.
            Resources without a matching live record are omitted.
        """
        service = KeaDHCPService.from_environment(env_name, provider_name, self.config_dir)
        existing = service.search_dhcpv6_subnets()
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
        managed_keys: set[str] | None = None,
        managed_subnets: list[ResourceConfig] | None = None,
        dependent_resources: list[ResourceConfig] | None = None,
        managed_dependent_resources: list[ResourceConfig] | None = None,
        deletes_only: bool = False,
    ) -> _Diff:
        """Compute the add/update/delete diff against live state.

        Adds carry the wire-format ``subnet_data`` dict (with the
        operator-facing ``name`` injected as ``__name__`` so ``apply``
        can attribute outcomes); updates carry ``(uuid, subnet_data)``;
        deletes carry ``(uuid, subnet_address)`` for synthetic-name
        construction. With ``managed_keys`` set, live subnets outside it are
        reported in ``unmanaged`` instead of ``deletes``.

        A delete is refused (moved to ``blocked``, with a warning) while a reservation
        InfraFoundry will not delete still uses the subnet (#1264). With ``deletes_only``
        the reservation phase has run, so any live reservation on the subnet blocks it;
        otherwise the reservations apply will delete are predicted from
        ``dependent_resources`` and ``managed_dependent_resources``.
        """
        existing = service.search_dhcpv6_subnets()
        existing_by_subnet = {str(s.get("subnet", "")): str(s.get("uuid", "")) for s in existing}

        adds: list[dict[str, Any]] = []
        updates: list[tuple[str, dict[str, Any]]] = []
        seen_subnets: set[str] = set()

        for resource in resources:
            subnet_data = _build_subnet_payload(resource)
            subnet_address = str(subnet_data["subnet"])
            seen_subnets.add(subnet_address)
            if deletes_only:
                continue

            existing_uuid = existing_by_subnet.get(subnet_address)
            if existing_uuid:
                current = service.get_dhcpv6_subnet(existing_uuid)
                current_fields = _extract_subnet_fields(current)
                desired_fields = _build_desired_subnet_fields(subnet_data)
                _drop_non_round_trip_subnet_fields(current_fields, desired_fields)
                if current_fields != desired_fields:
                    _log_field_diff(
                        f"DHCPv6 subnet {resource.name}", current_fields, desired_fields
                    )
                    updates.append(
                        (existing_uuid, {**subnet_data, "__name__": resource.name}),
                    )
            else:
                adds.append({**subnet_data, "__name__": resource.name})

        deletes: list[tuple[str, str]] = []
        unmanaged: list[tuple[str, str]] = []
        if not add_only:
            for subnet_address, uuid in existing_by_subnet.items():
                if not subnet_address or subnet_address in seen_subnets:
                    continue
                if managed_keys is not None and subnet_address not in managed_keys:
                    unmanaged.append((uuid, subnet_address))
                    continue
                deletes.append((uuid, subnet_address))

        blocked: list[tuple[str, str, list[str]]] = []
        warnings: list[str] = []
        if deletes:
            live_reservations = service.search_dhcpv6_reservations()
            candidate_uuids = {uuid for uuid, _ in deletes}
            if deletes_only:
                kept = live_reservations_by_subnet(live_reservations, candidate_uuids, "duid")
            else:
                kept = reservations_kept_on_subnets(
                    live_reservations,
                    candidate_uuids,
                    yaml_reservations=dependent_resources or [],
                    managed_reservations=managed_dependent_resources,
                    name_to_cidr={
                        **_build_subnet_name_to_cidr(managed_subnets),
                        **_build_subnet_name_to_cidr(resources),
                    },
                    cidr_to_uuid={c: u for c, u in existing_by_subnet.items() if c and u},
                )
            deletes, blocked, warnings = split_blocked_deletes(deletes, kept, "kea.dhcp6.subnets")

        return _Diff(
            adds=adds,
            updates=updates,
            deletes=deletes,
            unmanaged=unmanaged,
            blocked=blocked,
            warnings=warnings,
        )


def _build_subnet_payload(resource: ResourceConfig) -> dict[str, Any]:
    """Build the wire-format payload sent to OPNsense for a subnet.

    Mirrors the original ``_generate_kea_dhcp6_resources`` construction
    shape so wire-level behavior is unchanged.

    Args:
        resource: DHCPv6 subnet resource (validated upstream).

    Returns:
        Dict suitable for passing to ``service.add_dhcpv6_subnet`` /
        ``service.update_dhcpv6_subnet``.
    """
    config = resource.config
    subnet_data: dict[str, Any] = {
        "subnet": config.get("subnet"),
        "interface": config.get("interface"),
    }

    # Pools is a newline-separated string of ranges
    if "pools" in config:
        pool_strings = [pool["range"] for pool in config["pools"]]
        subnet_data["pools"] = "\n".join(pool_strings)

    if "valid_lifetime" in config:
        subnet_data["valid_lifetime"] = str(config["valid_lifetime"])
    if "description" in config:
        subnet_data["description"] = config["description"]

    option_data: dict[str, str] = {}
    if "dns_servers" in config:
        option_data["dns_servers"] = ",".join(config["dns_servers"])
    if "dns_search_list" in config:
        option_data["domain_search"] = ",".join(config["dns_search_list"])
    if option_data:
        subnet_data["option_data"] = option_data

    return subnet_data
