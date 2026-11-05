"""OPNsense API client built on the opnsense-openapi package."""

import json
import logging
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import quote

import httpx
from opnsense_openapi import APIResponseError
from opnsense_openapi import OPNsenseClient as OpenAPIOPNsenseClient

if TYPE_CHECKING:  # pragma: no cover
    # opnsense-openapi lacks stubs; this keeps mypy satisfied without affecting runtime.
    pass

from infrafoundry.core.exceptions import APIError, AuthenticationError

from . import endpoints

logger = logging.getLogger(__name__)


class OPNsenseClient:
    """Thin wrapper around opnsense-openapi's client with InfraFoundry error handling."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        base_url: str,
        verify_ssl: bool = True,
        timeout: int = 30,
        proxy: str | None = None,
    ) -> None:
        """Initialize the OPNsense API client wrapper.

        Args:
            api_key: API key for HTTP Basic Auth.
            api_secret: API secret for HTTP Basic Auth.
            base_url: Base URL of the OPNsense instance.
            verify_ssl: Whether to verify TLS certificates.
            timeout: Per-request timeout in seconds.
            proxy: Optional proxy URL to route API traffic through (e.g.
                ``http://proxy:3128`` or ``socks5://127.0.0.1:1080``). ``None``
                (the default) connects directly. SOCKS proxies require the
                ``socksio`` package (the ``infrafoundry[socks]`` extra).
        """
        self._base_url = base_url
        self.client = OpenAPIOPNsenseClient(
            base_url=base_url,
            api_key=api_key,
            api_secret=api_secret,
            verify_ssl=verify_ssl,
            timeout=timeout,
            proxy=proxy,
            # Strict endpoint validation stays off (#1239): it needs a known box
            # version and cannot exempt the in-tree assign_settings extension. The
            # version is read explicitly by ``detect_version`` for the plan/doctor check.
            auto_detect_version=False,
        )

    def detect_version(self) -> str:
        """Read the OPNsense version through opnsense-openapi.

        Returns:
            The version string reported by the box (e.g. ``"26.1.6_2"``).

        Raises:
            APIError: If the library cannot determine the version.
        """
        try:
            return self.client.detect_version()
        except APIResponseError as e:
            raise APIError(
                f"Could not detect the OPNsense version: {e}",
                provider="opnsense",
            ) from e

    @property
    def base_url(self) -> str:
        """The OPNsense base URL this client targets.

        Used as the per-box cache key by the shared
        ``ensure_infrafoundry_category`` helper (#746) so that a single
        process talking to multiple OPNsense boxes keeps separate
        identity-marker UUID entries per box.
        """
        return self._base_url

    def request(
        self,
        method: str,
        endpoint: str,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an authenticated API request using opnsense-openapi."""
        parts = [p for p in endpoint.split("/") if p]
        if len(parts) < 3:
            raise ValueError(f"Invalid endpoint format: {endpoint}")

        module, controller, command, *extra = parts
        try:
            if method.upper() == "GET":
                response = self.client.get(module, controller, command, *extra, **(params or {}))
            else:
                response = self.client.post(module, controller, command, *extra, json=data or {})

            return response

        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code if e.response else None
            response_text = e.response.text if e.response else str(e)

            if status_code in (401, 403):
                raise AuthenticationError(
                    "OPNsense authentication failed",
                    status_code=status_code,
                    response=response_text,
                    provider="opnsense",
                ) from e

            raise APIError(
                f"OPNsense API request failed: {e}",
                status_code=status_code,
                response=response_text,
                provider="opnsense",
            ) from e
        except json.JSONDecodeError as e:
            raise APIError(
                "Invalid JSON response from OPNsense",
                response=str(e),
                provider="opnsense",
            ) from e


class KeaClient:
    """Kea DHCP-specific API operations.

    This class provides methods for managing Kea DHCPv4 and DHCPv6 subnets
    and reservations through the OPNsense API. It wraps the generic
    OPNsenseClient with domain-specific operations.

    The generic ``_crud_*`` helpers take an ``api_version`` parameter
    (``"dhcpv4"`` or ``"dhcpv6"``) so the same helper covers both wire
    families; the public per-version wrappers below dispatch to it.

    Args:
        client: OPNsenseClient instance for making authenticated requests

    Example:
        >>> client = OPNsenseClient(...)
        >>> kea = KeaClient(client)
        >>> subnets = kea.search_dhcp6_subnets()
        >>> subnet = kea.add_dhcp6_subnet({
        ...     "subnet": "fd00:db8:40:1::/64",
        ...     "pools": [{"pool": "fd00:db8:40:1::10-fd00:db8:40:1::ff00"}]
        ... })
    """

    def __init__(self, client: OPNsenseClient) -> None:
        self.client = client

    # Generic CRUD helper methods

    def _crud_search(self, api_version: str, resource_type: str) -> list[dict[str, Any]]:
        """Generic search operation for Kea DHCP resources.

        Args:
            api_version: Kea API version segment (``"dhcpv4"`` or ``"dhcpv6"``)
            resource_type: Resource type (e.g., "Subnet", "Reservation")

        Returns:
            List of resource dictionaries from the 'rows' field
        """
        ep = endpoints.KEA_CRUD[(api_version, resource_type)].search
        response = self.client.request(ep.method, ep.path())
        return cast(list[dict[str, Any]], response.get("rows", []))

    def _crud_get(self, api_version: str, resource_type: str, uuid: str) -> dict[str, Any]:
        """Generic get operation for a specific Kea DHCP resource.

        Args:
            api_version: Kea API version segment (``"dhcpv4"`` or ``"dhcpv6"``)
            resource_type: Resource type (e.g., "Subnet", "Reservation")
            uuid: Resource UUID

        Returns:
            Resource configuration dictionary
        """
        ep = endpoints.KEA_CRUD[(api_version, resource_type)].read
        return self.client.request(ep.method, ep.path(uuid=uuid))

    def _crud_add(
        self, api_version: str, resource_type: str, resource_key: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        """Generic add operation for a new Kea DHCP resource.

        Args:
            api_version: Kea API version segment (``"dhcpv4"`` or ``"dhcpv6"``)
            resource_type: Resource type (e.g., "Subnet", "Reservation")
            resource_key: Key to wrap data in request (e.g., "subnet4", "reservation")
            data: Resource configuration

        Returns:
            Response with 'result' field (uuid is NOT included in add responses)
        """
        ep = endpoints.KEA_CRUD[(api_version, resource_type)].add
        request_data = {resource_key: data}
        return self.client.request(ep.method, ep.path(), data=request_data)

    def _crud_update(
        self,
        api_version: str,
        resource_type: str,
        uuid: str,
        resource_key: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Generic update operation for an existing Kea DHCP resource.

        Args:
            api_version: Kea API version segment (``"dhcpv4"`` or ``"dhcpv6"``)
            resource_type: Resource type (e.g., "Subnet", "Reservation")
            uuid: Resource UUID
            resource_key: Key to wrap data in request (e.g., "subnet4", "reservation")
            data: Updated resource configuration

        Returns:
            Response with 'result' field
        """
        ep = endpoints.KEA_CRUD[(api_version, resource_type)].update
        request_data = {resource_key: data}
        return self.client.request(ep.method, ep.path(uuid=uuid), data=request_data)

    def _crud_delete(self, api_version: str, resource_type: str, uuid: str) -> dict[str, Any]:
        """Generic delete operation for a Kea DHCP resource.

        Args:
            api_version: Kea API version segment (``"dhcpv4"`` or ``"dhcpv6"``)
            resource_type: Resource type (e.g., "Subnet", "Reservation")
            uuid: Resource UUID

        Returns:
            Response with 'result' field
        """
        ep = endpoints.KEA_CRUD[(api_version, resource_type)].delete
        return self.client.request(ep.method, ep.path(uuid=uuid))

    # DHCPv4 Subnet operations

    def search_dhcp4_subnets(self) -> list[dict[str, Any]]:
        """Search for all DHCPv4 subnets.

        Returns:
            List of subnet dictionaries with 'uuid', 'subnet', 'description', etc.
        """
        return self._crud_search("dhcpv4", "Subnet")

    def get_dhcp4_subnet(self, uuid: str) -> dict[str, Any]:
        """Get a specific DHCPv4 subnet by UUID.

        Args:
            uuid: Subnet UUID

        Returns:
            Subnet configuration dictionary (raw envelope ``{"subnet4": {...}}``)
        """
        return self._crud_get("dhcpv4", "Subnet", uuid)

    def add_dhcp4_subnet(self, subnet_data: dict[str, Any]) -> dict[str, Any]:
        """Add a new DHCPv4 subnet.

        Args:
            subnet_data: Subnet configuration dictionary (DHCPv4 wire schema,
                OPNsense 26.1; #1165):
                - subnet: IPv4 subnet (e.g., "192.168.1.0/24")
                - interface: Interface name (e.g., "opt1")
                - pools: Newline-joined pool ranges
                - description: Operator description
                - option_data: Nested dict of DHCP options:
                  routers / domain_name_servers / ntp_servers /
                  domain_search (comma-separated) and domain_name (string)
                - option_data_autocollect: Auto-collect options ("0" / "1")

        Returns:
            Response with 'result' field (uuid is NOT included in add responses).
        """
        return self._crud_add("dhcpv4", "Subnet", "subnet4", subnet_data)

    def update_dhcp4_subnet(self, uuid: str, subnet_data: dict[str, Any]) -> dict[str, Any]:
        """Update an existing DHCPv4 subnet.

        Args:
            uuid: Subnet UUID
            subnet_data: Updated subnet configuration

        Returns:
            Response with 'result' field
        """
        return self._crud_update("dhcpv4", "Subnet", uuid, "subnet4", subnet_data)

    def delete_dhcp4_subnet(self, uuid: str) -> dict[str, Any]:
        """Delete a DHCPv4 subnet.

        Args:
            uuid: Subnet UUID

        Returns:
            Response with 'result' field
        """
        return self._crud_delete("dhcpv4", "Subnet", uuid)

    # DHCPv4 Reservation operations

    def search_dhcp4_reservations(self) -> list[dict[str, Any]]:
        """Search for all DHCPv4 reservations.

        Returns:
            List of reservation dictionaries with 'uuid', 'subnet', 'hw_address', etc.
        """
        return self._crud_search("dhcpv4", "Reservation")

    def get_dhcp4_reservation(self, uuid: str) -> dict[str, Any]:
        """Get a specific DHCPv4 reservation by UUID.

        Args:
            uuid: Reservation UUID

        Returns:
            Reservation configuration dictionary (raw envelope ``{"reservation": {...}}``)
        """
        return self._crud_get("dhcpv4", "Reservation", uuid)

    def add_dhcp4_reservation(self, reservation_data: dict[str, Any]) -> dict[str, Any]:
        """Add a new DHCPv4 reservation.

        Args:
            reservation_data: Reservation configuration with fields:
                - subnet: UUID of the subnet
                - hw_address: MAC address (e.g., "aa:bb:cc:dd:ee:ff")
                - ip_address: IPv4 address to reserve
                - hostname: Hostname for the reservation
                - description: Optional description

        Returns:
            Response with 'result' field (uuid is NOT included in add responses).
        """
        return self._crud_add("dhcpv4", "Reservation", "reservation", reservation_data)

    def update_dhcp4_reservation(
        self, uuid: str, reservation_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Update an existing DHCPv4 reservation.

        Args:
            uuid: Reservation UUID
            reservation_data: Updated reservation configuration

        Returns:
            Response with 'result' field
        """
        return self._crud_update("dhcpv4", "Reservation", uuid, "reservation", reservation_data)

    def delete_dhcp4_reservation(self, uuid: str) -> dict[str, Any]:
        """Delete a DHCPv4 reservation.

        Args:
            uuid: Reservation UUID

        Returns:
            Response with 'result' field
        """
        return self._crud_delete("dhcpv4", "Reservation", uuid)

    # DHCPv4 General Settings operations

    def get_dhcp4_general(self) -> dict[str, Any]:
        """Get Kea DHCPv4 general settings.

        Returns:
            General settings dictionary with 'dhcpv4' key containing
            'general' (with 'enabled', 'interfaces', etc.).
        """
        return self.client.request(endpoints.KEA_DHCPV4_GET.method, endpoints.KEA_DHCPV4_GET.path())

    def set_dhcp4_general(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Update Kea DHCPv4 general settings.

        Args:
            settings: General settings to update, wrapped in 'dhcpv4' key.
                Example: {"dhcpv4": {"general": {"enabled": "1", "interfaces": "opt1,opt2"}}}

        Returns:
            Response with 'result' field
        """
        return self.client.request(
            endpoints.KEA_DHCPV4_SET.method, endpoints.KEA_DHCPV4_SET.path(), data=settings
        )

    def ensure_dhcp4_enabled(self, interfaces: list[str]) -> None:
        """Ensure Kea DHCPv4 is enabled with the specified interfaces selected.

        Mirrors :meth:`ensure_dhcp6_enabled` for the DHCPv4 controller. Reads
        current settings, enables the service if needed, and adds any missing
        interfaces to the selection. Only makes API calls if changes are
        required.

        Args:
            interfaces: List of interface names that must be enabled
                (e.g., ``["opt1", "opt2"]``).
        """
        general = self.get_dhcp4_general()
        # API returns: {"dhcpv4": {"general": {"enabled": "0", "interfaces": {...}}}}
        general_settings = general.get("dhcpv4", {}).get("general", {})

        currently_enabled = general_settings.get("enabled", "0") == "1"

        current_interfaces_raw = general_settings.get("interfaces", {})
        selected_interfaces: set[str] = set()

        if isinstance(current_interfaces_raw, dict):
            for iface_name, iface_data in current_interfaces_raw.items():
                if isinstance(iface_data, dict) and iface_data.get("selected", 0):
                    selected_interfaces.add(iface_name)
        elif isinstance(current_interfaces_raw, str) and current_interfaces_raw:
            selected_interfaces = set(current_interfaces_raw.split(","))

        required = set(interfaces)
        missing_interfaces = required - selected_interfaces
        needs_enable = not currently_enabled
        needs_interface_update = bool(missing_interfaces)

        if not needs_enable and not needs_interface_update:
            logger.info("Kea DHCPv4 already enabled with required interfaces")
            return

        new_interfaces = selected_interfaces | required
        update_data: dict[str, Any] = {
            "dhcpv4": {
                "general": {
                    "enabled": "1",
                    "interfaces": ",".join(sorted(new_interfaces)),
                }
            }
        }

        if needs_enable:
            print("Enabling Kea DHCPv4 service...")
        if needs_interface_update:
            print(f"Adding interfaces to DHCPv4: {', '.join(sorted(missing_interfaces))}")

        result = self.set_dhcp4_general(update_data)
        if result.get("result") == "failed":
            validations = result.get("validations", {})
            raise ValueError(f"Failed to update DHCPv4 general settings: {validations}")

        # Reconfigure to apply the general settings change
        self.reconfigure_service()
        print("Kea DHCPv4 service configured and running")

    # DHCPv6 Subnet operations

    def search_dhcp6_subnets(self) -> list[dict[str, Any]]:
        """Search for all DHCPv6 subnets.

        Returns:
            List of subnet dictionaries with 'uuid', 'subnet', 'interface', etc.
        """
        return self._crud_search("dhcpv6", "Subnet")

    def get_dhcp6_subnet(self, uuid: str) -> dict[str, Any]:
        """Get a specific DHCPv6 subnet by UUID.

        Args:
            uuid: Subnet UUID

        Returns:
            Subnet configuration dictionary
        """
        return self._crud_get("dhcpv6", "Subnet", uuid)

    def add_dhcp6_subnet(self, subnet_data: dict[str, Any]) -> dict[str, Any]:
        """Add a new DHCPv6 subnet.

        Args:
            subnet_data: Subnet configuration dictionary with fields:
                - subnet: IPv6 subnet (e.g., "fd00:db8:40:1::/64")
                - interface: Interface name (e.g., "opt6")
                - pools: List of pool dicts with "pool" field (e.g., "::10-::ff00")
                - option_data_autocollect: Auto-collect options (0 or 1)
                - valid_lifetime: Lease lifetime in seconds
                - dns_servers: Comma-separated DNS server IPv6 addresses
                - dns_search_list: Comma-separated DNS search domains

        Returns:
            Response with 'result' and 'uuid' fields
        """
        return self._crud_add("dhcpv6", "Subnet", "subnet6", subnet_data)

    def update_dhcp6_subnet(self, uuid: str, subnet_data: dict[str, Any]) -> dict[str, Any]:
        """Update an existing DHCPv6 subnet.

        Args:
            uuid: Subnet UUID
            subnet_data: Updated subnet configuration

        Returns:
            Response with 'result' field
        """
        return self._crud_update("dhcpv6", "Subnet", uuid, "subnet6", subnet_data)

    def delete_dhcp6_subnet(self, uuid: str) -> dict[str, Any]:
        """Delete a DHCPv6 subnet.

        Args:
            uuid: Subnet UUID

        Returns:
            Response with 'result' field
        """
        return self._crud_delete("dhcpv6", "Subnet", uuid)

    # DHCPv6 Reservation operations

    def search_dhcp6_reservations(self) -> list[dict[str, Any]]:
        """Search for all DHCPv6 reservations.

        Returns:
            List of reservation dictionaries with 'uuid', 'subnet_id', 'duid', etc.
        """
        return self._crud_search("dhcpv6", "Reservation")

    def get_dhcp6_reservation(self, uuid: str) -> dict[str, Any]:
        """Get a specific DHCPv6 reservation by UUID.

        Args:
            uuid: Reservation UUID

        Returns:
            Reservation configuration dictionary
        """
        return self._crud_get("dhcpv6", "Reservation", uuid)

    def add_dhcp6_reservation(self, reservation_data: dict[str, Any]) -> dict[str, Any]:
        """Add a new DHCPv6 reservation.

        Args:
            reservation_data: Reservation configuration with fields:
                - subnet_id: UUID of the subnet
                - duid: DHCP Unique Identifier (e.g., "00:01:00:01:2c:3d:...")
                - ip_addresses: IPv6 address to reserve
                - hostname: Hostname for the reservation
                - description: Optional description

        Returns:
            Response with 'result' and 'uuid' fields
        """
        return self._crud_add("dhcpv6", "Reservation", "reservation", reservation_data)

    def update_dhcp6_reservation(
        self, uuid: str, reservation_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Update an existing DHCPv6 reservation.

        Args:
            uuid: Reservation UUID
            reservation_data: Updated reservation configuration

        Returns:
            Response with 'result' field
        """
        return self._crud_update("dhcpv6", "Reservation", uuid, "reservation", reservation_data)

    def delete_dhcp6_reservation(self, uuid: str) -> dict[str, Any]:
        """Delete a DHCPv6 reservation.

        Args:
            uuid: Reservation UUID

        Returns:
            Response with 'result' field
        """
        return self._crud_delete("dhcpv6", "Reservation", uuid)

    # DHCPv6 General Settings operations

    def get_dhcp6_general(self) -> dict[str, Any]:
        """Get Kea DHCPv6 general settings.

        Returns:
            General settings dictionary with 'dhcpv6' key containing
            'enabled', 'interfaces', and other configuration.
        """
        return self.client.request(endpoints.KEA_DHCPV6_GET.method, endpoints.KEA_DHCPV6_GET.path())

    def set_dhcp6_general(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Update Kea DHCPv6 general settings.

        Args:
            settings: General settings to update, wrapped in 'dhcpv6' key.
                Example: {"dhcpv6": {"enabled": "1", "interfaces": "opt1,opt2"}}

        Returns:
            Response with 'result' field
        """
        return self.client.request(
            endpoints.KEA_DHCPV6_SET.method, endpoints.KEA_DHCPV6_SET.path(), data=settings
        )

    def ensure_dhcp6_enabled(self, interfaces: list[str]) -> None:
        """Ensure Kea DHCPv6 is enabled with the specified interfaces selected.

        Reads current settings, enables the service if needed, and adds any
        missing interfaces to the selection. Only makes API calls if changes
        are required.

        Args:
            interfaces: List of interface names that must be enabled (e.g., ["opt1", "opt2"])
        """
        general = self.get_dhcp6_general()
        # API returns: {"dhcpv6": {"general": {"enabled": "0", "interfaces": {...}}}}
        general_settings = general.get("dhcpv6", {}).get("general", {})

        # Determine current state
        currently_enabled = general_settings.get("enabled", "0") == "1"

        # Parse current interfaces — the API returns a dict of interface options
        # with "selected" field indicating which are active
        current_interfaces_raw = general_settings.get("interfaces", {})
        selected_interfaces: set[str] = set()

        if isinstance(current_interfaces_raw, dict):
            for iface_name, iface_data in current_interfaces_raw.items():
                if isinstance(iface_data, dict) and iface_data.get("selected", 0):
                    selected_interfaces.add(iface_name)
        elif isinstance(current_interfaces_raw, str) and current_interfaces_raw:
            selected_interfaces = set(current_interfaces_raw.split(","))

        # Determine required changes
        required = set(interfaces)
        missing_interfaces = required - selected_interfaces
        needs_enable = not currently_enabled
        needs_interface_update = bool(missing_interfaces)

        if not needs_enable and not needs_interface_update:
            logger.info("Kea DHCPv6 already enabled with required interfaces")
            return

        # Build update payload — must nest under dhcpv6.general to match API structure
        new_interfaces = selected_interfaces | required
        update_data: dict[str, Any] = {
            "dhcpv6": {
                "general": {
                    "enabled": "1",
                    "interfaces": ",".join(sorted(new_interfaces)),
                }
            }
        }

        if needs_enable:
            print("Enabling Kea DHCPv6 service...")
        if needs_interface_update:
            print(f"Adding interfaces to DHCPv6: {', '.join(sorted(missing_interfaces))}")

        result = self.set_dhcp6_general(update_data)
        if result.get("result") == "failed":
            validations = result.get("validations", {})
            raise ValueError(f"Failed to update DHCPv6 general settings: {validations}")

        # Reconfigure to apply the general settings change
        self.reconfigure_service()
        print("Kea DHCPv6 service configured and running")

    # Service operations

    def reconfigure_service(self) -> dict[str, Any]:
        """Reconfigure the Kea service to apply changes.

        This should be called after adding, updating, or deleting subnets
        or reservations to activate the changes.

        Returns:
            Response with 'status' field (should be 'ok')
        """
        return self.client.request(
            endpoints.KEA_RECONFIGURE.method, endpoints.KEA_RECONFIGURE.path()
        )


class SystemClient:
    """OPNsense ``<system>`` block API operations (#806).

    Wraps :class:`OPNsenseClient` with one ``get_*_settings`` /
    ``set_*_settings`` pair per ``opnsense.system.*`` singleton surface
    plus the firmware plugin install/lock/remove verbs. Each pair lines
    up with a singleton component manager declared in
    ``OPNsenseProvider.get_direct_api_resource_types()``.

    ``system.firmware`` and ``system.tuning`` use the 26.1 ``core/firmware``
    and ``core/tunables`` controllers (#1149): the reads were verified live
    on 26.1.6_2, the writes follow the MVC convention and are unverified.
    The general/settings/gdrivebackup methods are retained but 404 on 26.1;
    their types are unsupported.

    Args:
        client: ``OPNsenseClient`` instance for making authenticated requests.
    """

    def __init__(self, client: OPNsenseClient) -> None:
        """Initialize SystemClient with an OPNsense client wrapper."""
        self.client = client

    # ------------------------------------------------------------------
    # system.hostname (and shared with system.dns; see services for split)
    # ------------------------------------------------------------------

    def get_general_settings(self) -> dict[str, Any]:
        """Fetch the OPNsense system general settings (hostname/domain/dns).

        404 on 26.1; type is unsupported (#1149).

        Returns:
            Raw API response. The wire envelope is typically nested under
            ``{"general": {...}}`` or ``{"system": {"general": {...}}}`` —
            services normalize either shape via ``extract_*_fields``.
        """
        return self.client.request(
            endpoints.SYSTEM_GENERAL_GET.method, endpoints.SYSTEM_GENERAL_GET.path()
        )

    def set_general_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Update OPNsense system general settings.

        404 on 26.1; type is unsupported (#1149).

        Args:
            settings: Settings payload, typically wrapped in a ``general``
                or ``system.general`` envelope (matches the GET shape).

        Returns:
            Response with ``result`` field (e.g., ``"saved"``).
        """
        return self.client.request(
            endpoints.SYSTEM_GENERAL_SET.method, endpoints.SYSTEM_GENERAL_SET.path(), data=settings
        )

    # ------------------------------------------------------------------
    # system.ssh / system.webgui (shared system/settings controller)
    # ------------------------------------------------------------------

    def get_system_settings(self) -> dict[str, Any]:
        """Fetch the OPNsense system settings (ssh + webgui subkeys).

        404 on 26.1; type is unsupported (#1149).

        Returns:
            Raw API response. Subkeys ``ssh`` and ``webgui`` are read by
            the per-surface services.
        """
        return self.client.request(
            endpoints.SYSTEM_SETTINGS_GET.method, endpoints.SYSTEM_SETTINGS_GET.path()
        )

    def set_system_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Update OPNsense system settings.

        404 on 26.1; type is unsupported (#1149).

        Args:
            settings: Payload for the ssh/webgui sub-blocks. The caller is
                responsible for wrapping under the correct envelope.

        Returns:
            Response with ``result`` field.
        """
        return self.client.request(
            endpoints.SYSTEM_SETTINGS_SET.method,
            endpoints.SYSTEM_SETTINGS_SET.path(),
            data=settings,
        )

    # ------------------------------------------------------------------
    # system.firmware
    # ------------------------------------------------------------------

    def get_firmware_info(self) -> dict[str, Any]:
        """Fetch firmware info: version metadata plus the plugin/package list.

        Verified live on OPNsense 26.1.6_2.

        Returns:
            Raw API response; the ``package`` / ``plugin`` lists carry an
            ``installed`` flag (string ``"0"``/``"1"``).
        """
        return self.client.request(endpoints.FIRMWARE_INFO.method, endpoints.FIRMWARE_INFO.path())

    def get_firmware_settings(self) -> dict[str, Any]:
        """Fetch firmware settings (mirror, flavour, type, ...).

        Verified live on OPNsense 26.1.6_2.

        Returns:
            Raw response; settings live under the ``firmware`` key.
        """
        return self.client.request(endpoints.FIRMWARE_GET.method, endpoints.FIRMWARE_GET.path())

    def set_firmware_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Update firmware settings.

        Verified live on OPNsense 26.1.6_2 (``reboot`` 0 -> 1 -> 0); the
        ``{"firmware": {...}}`` partial payload follows the MVC ``setBase``
        convention (#1149).

        Args:
            payload: ``{"firmware": {<field>: <value>}}``.

        Returns:
            Response with ``result`` field.
        """
        return self.client.request(
            endpoints.FIRMWARE_SET.method, endpoints.FIRMWARE_SET.path(), data=payload
        )

    def install_plugin(self, name: str) -> dict[str, Any]:
        """Install a single OPNsense plugin (e.g., ``os-acme-client``).

        The request reaches OPNsense on 26.1.6_2, but it only queues a
        background job: the response acknowledges the request, not the
        install. A box that is out of date refuses the install in the job
        log. Poll :meth:`get_upgrade_status` and re-read
        :meth:`get_firmware_info` to learn the outcome (#1238).

        Args:
            name: Plugin name; percent-encoded into the URL path.

        Returns:
            API response (typically a job-acknowledgement payload).
        """
        return self.client.request(
            endpoints.FIRMWARE_INSTALL.method,
            endpoints.FIRMWARE_INSTALL.path(name=quote(name, safe="")),
        )

    def get_upgrade_status(self) -> dict[str, Any]:
        """Fetch the status of the running or last firmware background job.

        ``GET core/firmware/upgradestatus`` is in the 26.1.6 spec. The
        response carries ``status`` (``"running"`` while the job runs) and
        ``log`` (the job log); its shape beyond those two keys is not
        verified live (#1238).

        Returns:
            Raw API response.
        """
        return self.client.request(
            endpoints.FIRMWARE_UPGRADESTATUS.method, endpoints.FIRMWARE_UPGRADESTATUS.path()
        )

    def remove_plugin(self, name: str) -> dict[str, Any]:
        """Remove an OPNsense plugin (unverified; apply never calls this).

        Args:
            name: Plugin name to remove; percent-encoded into the URL path.

        Returns:
            API response.
        """
        return self.client.request(
            endpoints.FIRMWARE_REMOVE.method,
            endpoints.FIRMWARE_REMOVE.path(name=quote(name, safe="")),
        )

    def lock_plugin(self, name: str) -> dict[str, Any]:
        """Pin a plugin to its current version (unverified; apply never calls this).

        Args:
            name: Plugin name to lock; percent-encoded into the URL path.

        Returns:
            API response.
        """
        return self.client.request(
            endpoints.FIRMWARE_LOCK.method, endpoints.FIRMWARE_LOCK.path(name=quote(name, safe=""))
        )

    # ------------------------------------------------------------------
    # system.remotebackup (gdrivebackup MVC)
    # ------------------------------------------------------------------

    def get_remotebackup_settings(self) -> dict[str, Any]:
        """Fetch OPNsense remote-backup (Google Drive) settings.

        404 on 26.1; type is unsupported (#1149).

        Returns:
            Raw API response. The wire envelope is typically
            ``{"gdrivebackup": {"general": {...}}}`` (modern MVC) or
            ``{"general": {...}}`` — services normalize either shape.
        """
        return self.client.request(
            endpoints.GDRIVEBACKUP_GET.method, endpoints.GDRIVEBACKUP_GET.path()
        )

    def set_remotebackup_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Update OPNsense remote-backup (Google Drive) settings.

        404 on 26.1; type is unsupported (#1149).

        Args:
            settings: Payload (envelope matches the GET shape).

        Returns:
            Response with ``result`` field.
        """
        return self.client.request(
            endpoints.GDRIVEBACKUP_SET.method, endpoints.GDRIVEBACKUP_SET.path(), data=settings
        )

    # ------------------------------------------------------------------
    # system.tuning (sysctl tunables)
    # ------------------------------------------------------------------

    def get_tunables(self) -> dict[str, Any]:
        """Fetch all system tunables (sysctl).

        Verified live on OPNsense 26.1.6_2.

        Returns:
            Raw response; items live under ``sysctl.item``, keyed by uuid.
        """
        return self.client.request(endpoints.TUNABLES_GET.method, endpoints.TUNABLES_GET.path())

    def add_tunable(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Add a tunable. Verified live on 26.1.6_2 (58 -> 59 entries, #1238).

        Args:
            payload: ``{"sysctl": {"tunable": ..., "value": ..., "descr": ...}}``.

        Returns:
            Response with ``result`` field.
        """
        return self.client.request(
            endpoints.TUNABLES_ADD.method, endpoints.TUNABLES_ADD.path(), data=payload
        )

    def set_tunable(self, uuid: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Update a tunable by uuid. Verified live on 26.1.6_2 (changed, then reverted).

        Args:
            uuid: Tunable uuid; percent-encoded into the URL path.
            payload: ``{"sysctl": {...}}``.

        Returns:
            Response with ``result`` field.
        """
        return self.client.request(
            endpoints.TUNABLES_SET.method,
            endpoints.TUNABLES_SET.path(uuid=quote(uuid, safe="")),
            data=payload,
        )

    def del_tunable(self, uuid: str) -> dict[str, Any]:
        """Delete a tunable by uuid. Verified by hand on 26.1.6_2; apply never calls this.

        Args:
            uuid: Tunable uuid; percent-encoded into the URL path.

        Returns:
            Response with ``result`` field.
        """
        return self.client.request(
            endpoints.TUNABLES_DEL.method, endpoints.TUNABLES_DEL.path(uuid=quote(uuid, safe=""))
        )

    def reconfigure_tunables(self) -> dict[str, Any]:
        """Apply pending tunable changes. Verified live on 26.1.6_2 (re-plan stable).

        Returns:
            Response with ``status`` field.
        """
        return self.client.request(
            endpoints.TUNABLES_RECONFIGURE.method, endpoints.TUNABLES_RECONFIGURE.path()
        )


class RadvdClient:
    """OPNsense ``radvd`` (IPv6 Router Advertisement) MVC API operations (#788).

    Wraps :class:`OPNsenseClient` with the per-entry CRUD verbs the modern
    radvd controller exposes. Endpoint shapes verified live against
    ``fw-prod`` (2026-05-10 probe captured in
    ``tmp/agents/claude/probe-788.md``):

    - ``GET radvd/settings/get`` — bulk read (``{"radvd": {"entries": [...]}}``).
    - ``POST radvd/settings/searchEntry`` — paginated list (``{"rows": [...]}``).
    - ``GET radvd/settings/getEntry/<uuid>`` — single record.
    - ``POST radvd/settings/addEntry`` — create.
    - ``POST radvd/settings/setEntry/<uuid>`` — update.
    - ``POST radvd/settings/delEntry/<uuid>`` — delete.
    - ``POST radvd/service/reconfigure`` — apply pending changes.
    - ``GET radvd/service/status`` — daemon health.

    Args:
        client: ``OPNsenseClient`` instance for making authenticated requests.
    """

    def __init__(self, client: OPNsenseClient) -> None:
        """Initialize RadvdClient with an OPNsense client wrapper."""
        self.client = client

    def search_records(self) -> list[dict[str, Any]]:
        """Search for all radvd per-interface entries.

        Returns:
            List of entry dictionaries (each carrying ``uuid`` plus the
            wire schema fields). Empty list when no entries exist.
        """
        response = self.client.request(endpoints.RADVD.search.method, endpoints.RADVD.search.path())
        return cast(list[dict[str, Any]], response.get("rows", []))

    def get_record(self, uuid: str) -> dict[str, Any]:
        """Fetch a specific radvd entry by UUID.

        Args:
            uuid: Entry UUID.

        Returns:
            Entry configuration dictionary (wire envelope).
        """
        return self.client.request(
            endpoints.RADVD.read.method, endpoints.RADVD.read.path(uuid=uuid)
        )

    def add_record(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a new radvd entry.

        Args:
            payload: Wire payload wrapped under ``"entry"``.

        Returns:
            API response (typically ``{"result": "saved", "uuid": "..."}``).
        """
        return self.client.request(
            endpoints.RADVD.add.method, endpoints.RADVD.add.path(), data=payload
        )

    def set_record(self, uuid: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Update an existing radvd entry.

        Args:
            uuid: Entry UUID.
            payload: Wire payload wrapped under ``"entry"``.

        Returns:
            API response (typically ``{"result": "saved"}``).
        """
        return self.client.request(
            endpoints.RADVD.update.method, endpoints.RADVD.update.path(uuid=uuid), data=payload
        )

    def del_record(self, uuid: str) -> dict[str, Any]:
        """Delete a radvd entry.

        Args:
            uuid: Entry UUID.

        Returns:
            API response.
        """
        return self.client.request(
            endpoints.RADVD.delete.method, endpoints.RADVD.delete.path(uuid=uuid)
        )

    def reconfigure(self) -> dict[str, Any]:
        """Reconfigure the radvd daemon to apply pending changes.

        Returns:
            API response (typically ``{"status": "ok"}``).
        """
        return self.client.request(
            endpoints.RADVD_RECONFIGURE.method, endpoints.RADVD_RECONFIGURE.path()
        )

    def get_service_status(self) -> dict[str, Any]:
        """Fetch radvd daemon status.

        Returns:
            API response (typically ``{"status": "running" | "stopped" | "unknown"}``).
        """
        return self.client.request(endpoints.RADVD_STATUS.method, endpoints.RADVD_STATUS.path())

    def get_settings(self) -> dict[str, Any]:
        """Bulk read of all radvd entries via the settings/get endpoint.

        Returns:
            ``{"radvd": {"entries": [...]}}`` envelope.
        """
        return self.client.request(
            endpoints.RADVD_SETTINGS_GET.method, endpoints.RADVD_SETTINGS_GET.path()
        )


class CronClient:
    """OPNsense ``cron`` (scheduled jobs) MVC API operations (#789).

    Wraps :class:`OPNsenseClient` with the per-job CRUD verbs the
    ``cron/settings/`` controller exposes. Endpoint shapes are based on the
    expected OPNsense core-cron MVC surface; adjust the path constants
    below if the live box uses a different prefix.

    Endpoints (expected):

    - ``POST cron/settings/searchJobs`` — paginated list (``{"rows": [...]}``)
    - ``GET cron/settings/getJob/<uuid>`` — single job record.
    - ``POST cron/settings/addJob`` — create.
    - ``POST cron/settings/setJob/<uuid>`` — update.
    - ``POST cron/settings/delJob/<uuid>`` — delete.
    - ``POST cron/service/reconfigure`` — apply pending changes.

    Args:
        client: ``OPNsenseClient`` instance for making authenticated requests.
    """

    def __init__(self, client: OPNsenseClient) -> None:
        """Initialize CronClient with an OPNsense client wrapper."""
        self.client = client

    def search_jobs(self) -> list[dict[str, Any]]:
        """Search for all scheduled cron jobs.

        Returns:
            List of job dictionaries (each carrying ``uuid`` plus the
            wire schema fields). Empty list when no jobs exist.
        """
        response = self.client.request(endpoints.CRON.search.method, endpoints.CRON.search.path())
        return cast(list[dict[str, Any]], response.get("rows", []))

    def get_job(self, uuid: str) -> dict[str, Any]:
        """Fetch a specific cron job by UUID.

        Args:
            uuid: Job UUID.

        Returns:
            Job configuration dictionary (wire envelope).
        """
        return self.client.request(endpoints.CRON.read.method, endpoints.CRON.read.path(uuid=uuid))

    def add_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a new cron job.

        Args:
            payload: Wire payload wrapped under ``"job"``.

        Returns:
            API response (typically ``{"result": "saved", "uuid": "..."}``).
        """
        return self.client.request(
            endpoints.CRON.add.method, endpoints.CRON.add.path(), data=payload
        )

    def set_job(self, uuid: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Update an existing cron job.

        Args:
            uuid: Job UUID.
            payload: Wire payload wrapped under ``"job"``.

        Returns:
            API response (typically ``{"result": "saved"}``).
        """
        return self.client.request(
            endpoints.CRON.update.method, endpoints.CRON.update.path(uuid=uuid), data=payload
        )

    def del_job(self, uuid: str) -> dict[str, Any]:
        """Delete a cron job.

        Args:
            uuid: Job UUID.

        Returns:
            API response.
        """
        return self.client.request(
            endpoints.CRON.delete.method, endpoints.CRON.delete.path(uuid=uuid)
        )

    def reconfigure(self) -> dict[str, Any]:
        """Reconfigure the cron service to apply pending changes.

        Returns:
            API response (typically ``{"status": "ok"}``).
        """
        return self.client.request(
            endpoints.CRON_RECONFIGURE.method, endpoints.CRON_RECONFIGURE.path()
        )
