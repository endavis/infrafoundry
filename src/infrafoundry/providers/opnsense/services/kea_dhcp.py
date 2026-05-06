"""Kea DHCP service for OPNsense operations.

Module-private helpers prefixed with an underscore (``_normalize_field_value``,
``_select_option_dict_value``, ``_extract_*``, ``_build_desired_*``,
``_drop_non_round_trip_subnet_fields``, ``_log_field_diff``,
``_ASYMMETRIC_SUBNET_FIELDS``) implement the DHCPv6 change-detection
contract shared between :class:`KeaDHCPv6SubnetManager` and
:class:`KeaDHCPv6ReservationManager`. They were relocated from
``providers/opnsense/__init__.py`` in #758 (byte-identical move; see the
ADR-0014 per-component decision for ``kea_dhcp6``) so both managers can
reuse them without provider coupling.
"""

import logging
from typing import Any, Final

import yaml

from ..api_client import KeaClient, OPNsenseClient
from .base import BaseService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DHCPv6 change-detection helpers (relocated from providers/opnsense/__init__.py
# in #758 — byte-identical move so PR #757's regression fixes survive intact).
# ---------------------------------------------------------------------------


def _normalize_field_value(value: str) -> str:
    """Normalize a field value for comparison.

    Strips leading/trailing whitespace and sorts newline-separated lines
    (e.g., pool ranges) so ordering differences don't cause false positives.

    Args:
        value: Raw string field value

    Returns:
        Normalized string value
    """
    stripped = value.strip()
    if "\n" in stripped:
        lines = [line.strip() for line in stripped.split("\n") if line.strip()]
        return "\n".join(sorted(lines))
    return stripped


def _select_option_dict_value(raw: Any) -> str:
    """Normalize an OPNsense ``selected``-style field for comparison.

    Several OPNsense API GET responses return select-style fields as nested
    option-dicts of the form ``{"<key>": {"value": "...", "selected": 0|1}}``
    rather than as plain strings.  This helper normalizes either shape into a
    single comparable string:

    - ``dict``: returns the comma-joined sorted list of keys whose entry has
      ``selected`` truthy.  Returns an empty string when no entry is selected
      (including the live shape ``{"": {"value": "", "selected": 1}}`` that
      OPNsense uses to represent an unset value).
    - ``str`` / ``None`` / missing: normalized via :func:`_normalize_field_value`
      (whitespace-stripped, multi-line sorted) — preserves the original
      plain-string path for OPNsense versions that return strings here.

    Args:
        raw: Raw field value from an OPNsense API GET response.

    Returns:
        Normalized string suitable for equality comparison against the
        plain-string form built by ``_build_desired_*_fields``.
    """
    if isinstance(raw, dict):
        selected = [
            key for key, info in raw.items() if isinstance(info, dict) and info.get("selected", 0)
        ]
        # Filter empty-string keys (OPNsense's "no selection" sentinel) so the
        # live shape ``{"": {..., "selected": 1}}`` extracts to "" — matching
        # the desired side which omits the field entirely.
        return ",".join(sorted(name for name in selected if name))
    return _normalize_field_value(str(raw or ""))


def _extract_subnet_fields(api_response: dict[str, Any]) -> dict[str, str]:
    """Extract and normalize subnet fields from an OPNsense GET response.

    The OPNsense API returns GET responses wrapped under a resource key
    (e.g., ``{"subnet6": {"subnet": "...", "interface": {...}, ...}}``).
    Select fields like ``interface`` and the ``option_data`` sub-fields
    ``dns_servers`` / ``domain_search`` may be returned as dicts with
    ``selected`` indicators (e.g. ``{"": {"value": "", "selected": 1}}``)
    rather than plain strings.  This helper normalizes those values via
    :func:`_select_option_dict_value` so they can be compared with the
    flat strings we send in update requests.

    Args:
        api_response: Raw response from ``get_dhcp6_subnet(uuid)``

    Returns:
        Flat dictionary of normalized field values (all strings)
    """
    data = api_response.get("subnet6", {})
    result: dict[str, str] = {}

    # Simple string fields — normalize whitespace and sort multi-line values
    for field in ("subnet", "pools", "valid_lifetime", "description"):
        result[field] = _normalize_field_value(str(data.get(field, "") or ""))

    # Interface may be a dict with selected keys or a plain string
    result["interface"] = _select_option_dict_value(data.get("interface", ""))

    # option_data sub-fields — OPNsense 25.7+ returns these as nested
    # option-dicts (e.g. ``{"": {"value": "", "selected": 1}}``) rather
    # than plain strings.  ``_select_option_dict_value`` normalizes either
    # shape so change-detection isn't fooled by a Python-repr mismatch.
    option_data = data.get("option_data", {})
    if isinstance(option_data, dict):
        result["option_data.dns_servers"] = _select_option_dict_value(
            option_data.get("dns_servers", "")
        )
        result["option_data.domain_search"] = _select_option_dict_value(
            option_data.get("domain_search", "")
        )
    else:
        result["option_data.dns_servers"] = ""
        result["option_data.domain_search"] = ""

    return result


def _extract_reservation_fields(api_response: dict[str, Any]) -> dict[str, str]:
    """Extract and normalize reservation fields from an OPNsense GET response.

    The OPNsense API returns GET responses wrapped under a resource key
    (e.g., ``{"reservation": {"ip_address": "...", ...}}``).
    The ``subnet`` field may be returned as a dict with ``selected``
    indicators.  This method normalizes values for comparison.

    Args:
        api_response: Raw response from ``get_dhcp6_reservation(uuid)``

    Returns:
        Flat dictionary of normalized field values (all strings)
    """
    data = api_response.get("reservation", {})
    result: dict[str, str] = {}

    # Simple string fields
    for field in ("ip_address", "duid", "hostname", "description"):
        result[field] = str(data.get(field, "") or "")

    # Subnet may be a dict with selected UUID or a plain string
    subnet_raw = data.get("subnet", "")
    if isinstance(subnet_raw, dict):
        selected = [
            uuid
            for uuid, info in subnet_raw.items()
            if isinstance(info, dict) and info.get("selected", 0)
        ]
        result["subnet"] = selected[0] if selected else ""
    else:
        result["subnet"] = str(subnet_raw or "")

    return result


def _build_desired_subnet_fields(subnet_data: dict[str, Any]) -> dict[str, str]:
    """Build a normalized field dict from the desired subnet data we send to the API.

    Args:
        subnet_data: Subnet configuration dict prepared for the update call

    Returns:
        Flat dictionary of normalized field values matching the format
        returned by ``_extract_subnet_fields``
    """
    result: dict[str, str] = {}
    for field in ("subnet", "pools", "valid_lifetime", "description"):
        result[field] = _normalize_field_value(str(subnet_data.get(field, "") or ""))
    result["interface"] = _normalize_field_value(str(subnet_data.get("interface", "") or ""))

    option_data = subnet_data.get("option_data", {})
    if isinstance(option_data, dict):
        result["option_data.dns_servers"] = _normalize_field_value(
            str(option_data.get("dns_servers", "") or "")
        )
        result["option_data.domain_search"] = _normalize_field_value(
            str(option_data.get("domain_search", "") or "")
        )
    else:
        result["option_data.dns_servers"] = ""
        result["option_data.domain_search"] = ""

    return result


def _build_desired_reservation_fields(
    reservation_data: dict[str, Any],
) -> dict[str, str]:
    """Build a normalized field dict from the desired reservation data.

    Args:
        reservation_data: Reservation configuration dict prepared for the update call

    Returns:
        Flat dictionary of normalized field values matching the format
        returned by ``_extract_reservation_fields``
    """
    result: dict[str, str] = {}
    for field in ("subnet", "ip_address", "duid", "hostname", "description"):
        result[field] = str(reservation_data.get(field, "") or "")
    return result


# Fields the OPNsense Kea DHCPv6 subnet API accepts on write but does not
# return on read (verified live on OPNsense 25.7.11_1: ``valid_lifetime``
# is sent on ``addSubnet``/``setSubnet`` but is absent from the
# ``getSubnet`` response). Comparing them produces unconditional
# false-positive diffs ("current=''" vs "desired='86400'") on every plan,
# which previously triggered spurious subnet updates + Kea reconfigure
# on every plan/apply. ``_drop_non_round_trip_subnet_fields`` strips them
# from comparison only when the live response is missing/empty for that
# field, so a future OPNsense version that does expose the value would
# re-engage normal change-detection automatically.
_ASYMMETRIC_SUBNET_FIELDS: Final[tuple[str, ...]] = ("valid_lifetime",)


def _drop_non_round_trip_subnet_fields(
    current_fields: dict[str, str],
    desired_fields: dict[str, str],
) -> None:
    """Drop subnet fields that the API doesn't round-trip via GET.

    Mutates both dicts in place. A field is dropped from both sides
    only when the live response is missing or empty for it — that
    way change-detection still works when the API does return the
    value (e.g., on a future OPNsense version).

    The desired-side payload sent by ``update_dhcp6_subnet`` still
    includes these fields, so apply continues to set them; this
    helper only governs whether a diff is *triggered* by them.
    """
    for field in _ASYMMETRIC_SUBNET_FIELDS:
        if not current_fields.get(field):
            current_fields.pop(field, None)
            desired_fields.pop(field, None)


def _log_field_diff(
    resource_name: str,
    current_fields: dict[str, str],
    desired_fields: dict[str, str],
) -> None:
    """Log field-by-field differences between current and desired state.

    Only logs when DEBUG level is enabled to avoid noise in normal operation.

    Args:
        resource_name: Human-readable name of the resource for log messages
        current_fields: Normalized fields extracted from the API response
        desired_fields: Normalized fields built from the desired configuration
    """
    if not logger.isEnabledFor(logging.DEBUG):
        return

    all_keys = sorted(set(current_fields) | set(desired_fields))
    for key in all_keys:
        current_val = current_fields.get(key, "<missing>")
        desired_val = desired_fields.get(key, "<missing>")
        if current_val != desired_val:
            logger.debug(
                "%s field %r differs: current=%r desired=%r",
                resource_name,
                key,
                current_val,
                desired_val,
            )


class KeaDHCPService(BaseService):
    """Service for Kea DHCP operations via OPNsense API.

    Provides low-level operations for managing Kea DHCPv4 and DHCPv6
    configurations including subnets, reservations, and service control.
    """

    def __init__(self, client: OPNsenseClient) -> None:
        """Initialize Kea DHCP service.

        Args:
            client: Configured OPNsense API client
        """
        super().__init__(client)
        self.kea_client = KeaClient(client)

    # DHCPv4 Operations
    def search_dhcpv4_reservations(self) -> list[dict[str, Any]]:
        """Search for all DHCPv4 reservations.

        Returns:
            List of reservation dictionaries with uuid, hostname, hw_address, etc.
        """
        response = self.client.request("GET", "kea/dhcpv4/searchReservation")
        return response.get("rows", []) if response else []

    def delete_dhcpv4_reservation(self, uuid: str) -> None:
        """Delete a DHCPv4 reservation by UUID.

        Args:
            uuid: Reservation UUID
        """
        self.client.request("POST", f"kea/dhcpv4/delReservation/{uuid}")

    def delete_all_dhcpv4_reservations(self) -> int:
        """Delete all DHCPv4 reservations.

        Returns:
            Number of reservations deleted
        """
        reservations = self.search_dhcpv4_reservations()
        count = 0
        for reservation in reservations:
            if uuid := reservation.get("uuid"):
                self.delete_dhcpv4_reservation(uuid)
                count += 1
        return count

    def search_dhcpv4_subnets(self) -> list[dict[str, Any]]:
        """Search for all DHCPv4 subnets.

        Returns:
            List of subnet dictionaries with uuid, subnet, description, etc.
        """
        response = self.client.request("GET", "kea/dhcpv4/searchSubnet")
        return response.get("rows", []) if response else []

    def delete_dhcpv4_subnet(self, uuid: str) -> None:
        """Delete a DHCPv4 subnet by UUID.

        Args:
            uuid: Subnet UUID
        """
        self.client.request("POST", f"kea/dhcpv4/delSubnet/{uuid}")

    def delete_all_dhcpv4_subnets(self) -> int:
        """Delete all DHCPv4 subnets.

        Returns:
            Number of subnets deleted
        """
        subnets = self.search_dhcpv4_subnets()
        count = 0
        for subnet in subnets:
            if uuid := subnet.get("uuid"):
                self.delete_dhcpv4_subnet(uuid)
                count += 1
        return count

    # DHCPv6 Operations
    def search_dhcpv6_reservations(self) -> list[dict[str, Any]]:
        """Search for all DHCPv6 reservations.

        Returns:
            List of reservation dictionaries
        """
        return self.kea_client.search_dhcp6_reservations()

    def get_dhcpv6_reservation(self, uuid: str) -> dict[str, Any]:
        """Get a single DHCPv6 reservation by UUID.

        Args:
            uuid: Reservation UUID

        Returns:
            Reservation configuration dictionary (raw envelope ``{"reservation": {...}}``)
        """
        return self.kea_client.get_dhcp6_reservation(uuid)

    def add_dhcpv6_reservation(self, reservation_data: dict[str, Any]) -> dict[str, Any]:
        """Add a new DHCPv6 reservation.

        Args:
            reservation_data: Reservation configuration dict (wire-format fields).

        Returns:
            API response (typically ``{"result": "saved"}``).
        """
        return self.kea_client.add_dhcp6_reservation(reservation_data)

    def update_dhcpv6_reservation(
        self, uuid: str, reservation_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Update an existing DHCPv6 reservation by UUID.

        Args:
            uuid: Reservation UUID.
            reservation_data: Reservation configuration dict (wire-format fields).

        Returns:
            API response.
        """
        return self.kea_client.update_dhcp6_reservation(uuid, reservation_data)

    def delete_dhcpv6_reservation(self, uuid: str) -> None:
        """Delete a DHCPv6 reservation by UUID.

        Args:
            uuid: Reservation UUID
        """
        self.kea_client.delete_dhcp6_reservation(uuid)

    def delete_all_dhcpv6_reservations(self) -> int:
        """Delete all DHCPv6 reservations.

        Returns:
            Number of reservations deleted
        """
        reservations = self.search_dhcpv6_reservations()
        count = 0
        for reservation in reservations:
            if uuid := reservation.get("uuid"):
                self.delete_dhcpv6_reservation(uuid)
                count += 1
        return count

    def search_dhcpv6_subnets(self) -> list[dict[str, Any]]:
        """Search for all DHCPv6 subnets.

        Returns:
            List of subnet dictionaries
        """
        return self.kea_client.search_dhcp6_subnets()

    def get_dhcpv6_subnet(self, uuid: str) -> dict[str, Any]:
        """Get a single DHCPv6 subnet by UUID.

        Args:
            uuid: Subnet UUID

        Returns:
            Subnet configuration dictionary (raw envelope ``{"subnet6": {...}}``)
        """
        return self.kea_client.get_dhcp6_subnet(uuid)

    def add_dhcpv6_subnet(self, subnet_data: dict[str, Any]) -> dict[str, Any]:
        """Add a new DHCPv6 subnet.

        Args:
            subnet_data: Subnet configuration dict (wire-format fields).

        Returns:
            API response (typically ``{"result": "saved"}``; the UUID is
            *not* included — callers must re-search to recover it).
        """
        return self.kea_client.add_dhcp6_subnet(subnet_data)

    def update_dhcpv6_subnet(self, uuid: str, subnet_data: dict[str, Any]) -> dict[str, Any]:
        """Update an existing DHCPv6 subnet by UUID.

        Args:
            uuid: Subnet UUID.
            subnet_data: Subnet configuration dict (wire-format fields).

        Returns:
            API response.
        """
        return self.kea_client.update_dhcp6_subnet(uuid, subnet_data)

    def delete_dhcpv6_subnet(self, uuid: str) -> None:
        """Delete a DHCPv6 subnet by UUID.

        Args:
            uuid: Subnet UUID
        """
        self.kea_client.delete_dhcp6_subnet(uuid)

    def ensure_dhcpv6_enabled(self, interfaces: list[str]) -> None:
        """Ensure Kea DHCPv6 is enabled with the specified interfaces selected.

        Thin pass-through to :meth:`KeaClient.ensure_dhcp6_enabled` so
        component managers do not need to reach through ``service.kea_client``.

        Args:
            interfaces: Interface names that must be enabled.
        """
        self.kea_client.ensure_dhcp6_enabled(interfaces)

    def delete_all_dhcpv6_subnets(self) -> int:
        """Delete all DHCPv6 subnets.

        Returns:
            Number of subnets deleted
        """
        subnets = self.search_dhcpv6_subnets()
        count = 0
        for subnet in subnets:
            if uuid := subnet.get("uuid"):
                self.delete_dhcpv6_subnet(uuid)
                count += 1
        return count

    # Service Control
    def reconfigure(self) -> None:
        """Reconfigure Kea DHCP service to apply changes."""
        self.client.request("POST", "kea/service/reconfigure")

    # Export Operations
    def export_to_yaml(self) -> str:
        """Export current Kea DHCP configuration to YAML.

        Exports both DHCPv4 and DHCPv6 configurations in InfraFoundry
        resource-centric format.

        Returns:
            YAML string containing all Kea DHCP resources
        """
        resources = []

        # Export DHCPv4 subnets
        dhcpv4_subnets = self.search_dhcpv4_subnets()
        for subnet in dhcpv4_subnets:
            resource = {
                "provider": "opnsense",
                "type": "kea_subnet",
                "name": subnet.get("description", "").lower().replace(" ", "_"),
                "config": {
                    "subnet": subnet.get("subnet", ""),
                    "pools": subnet.get("pools", []),
                    "description": subnet.get("description", ""),
                },
            }
            # Add optional fields if present
            if subnet.get("option_data_autocollect") == "1":
                resource["config"]["auto_collect"] = True
            if dns_servers := subnet.get("option_data_dns_servers"):
                resource["config"]["dns_servers"] = [s.strip() for s in dns_servers.split(",")]
            if routers := subnet.get("option_data_routers"):
                resource["config"]["routers"] = [r.strip() for r in routers.split(",")]
            if domain_name := subnet.get("option_data_domain_name"):
                resource["config"]["domain_name"] = domain_name
            if ntp_servers := subnet.get("option_data_ntp_servers"):
                resource["config"]["ntp_servers"] = [n.strip() for n in ntp_servers.split(",")]

            resources.append(resource)

        # Export DHCPv4 reservations
        dhcpv4_reservations = self.search_dhcpv4_reservations()
        for reservation in dhcpv4_reservations:
            hostname = reservation.get("hostname", "")
            name = hostname.lower().replace(" ", "_").replace("-", "_")
            resource = {
                "provider": "opnsense",
                "type": "kea_reservation",
                "name": name,
                "config": {
                    "subnet": reservation.get("subnet", ""),
                    "hw_address": reservation.get("hw_address", ""),
                    "ip_address": reservation.get("ip_address", ""),
                },
            }
            if hostname:
                resource["config"]["hostname"] = hostname
            if description := reservation.get("description"):
                resource["config"]["description"] = description

            resources.append(resource)

        # Export DHCPv6 subnets
        dhcpv6_subnets = self.search_dhcpv6_subnets()
        for subnet in dhcpv6_subnets:
            resource = {
                "provider": "opnsense",
                "type": "kea_dhcp6_subnet",
                "name": f"{subnet.get('description', '').lower().replace(' ', '_')}_v6",
                "config": {
                    "subnet": subnet.get("subnet", ""),
                    "description": subnet.get("description", ""),
                },
            }
            # Add optional fields if present
            if subnet.get("option_data_autocollect") == "1":
                resource["config"]["auto_collect"] = True
            if dns_servers := subnet.get("option_data_dns_servers"):
                resource["config"]["dns_servers"] = [s.strip() for s in dns_servers.split(",")]
            if domain_search := subnet.get("option_data_domain_search"):
                resource["config"]["domain_search"] = [d.strip() for d in domain_search.split(",")]

            resources.append(resource)

        # Export DHCPv6 reservations
        dhcpv6_reservations = self.search_dhcpv6_reservations()
        for reservation in dhcpv6_reservations:
            hostname = reservation.get("hostname", "")
            name = f"{hostname.lower().replace(' ', '_').replace('-', '_')}_v6"
            resource = {
                "provider": "opnsense",
                "type": "kea_dhcp6_reservation",
                "name": name,
                "config": {
                    "subnet": reservation.get("subnet", ""),
                    "ip_address": reservation.get("ip_address", ""),
                },
            }
            if duid := reservation.get("duid"):
                resource["config"]["duid"] = duid
            if hostname:
                resource["config"]["hostname"] = hostname
            if description := reservation.get("description"):
                resource["config"]["description"] = description

            resources.append(resource)

        # Generate YAML
        config = {"resources": resources}
        return yaml.dump(config, default_flow_style=False, sort_keys=False)
