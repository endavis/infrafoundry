"""OPNsense API client built on the opnsense-openapi package."""

import json
import logging
from typing import TYPE_CHECKING, Any, cast

import httpx
from opnsense_openapi import OPNsenseClient as OpenAPIOPNsenseClient

if TYPE_CHECKING:  # pragma: no cover
    # opnsense-openapi lacks stubs; this keeps mypy satisfied without affecting runtime.
    pass

from infrafoundry.core.exceptions import APIError, AuthenticationError

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
            auto_detect_version=False,
        )

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
        ...     "subnet": "fd00:3742:40:1::/64",
        ...     "pools": [{"pool": "fd00:3742:40:1::10-fd00:3742:40:1::ff00"}]
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
        endpoint = f"kea/{api_version}/search{resource_type}"
        response = self.client.request("GET", endpoint)
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
        endpoint = f"kea/{api_version}/get{resource_type}/{uuid}"
        return self.client.request("GET", endpoint)

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
        endpoint = f"kea/{api_version}/add{resource_type}"
        request_data = {resource_key: data}
        return self.client.request("POST", endpoint, data=request_data)

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
        endpoint = f"kea/{api_version}/set{resource_type}/{uuid}"
        request_data = {resource_key: data}
        return self.client.request("POST", endpoint, data=request_data)

    def _crud_delete(self, api_version: str, resource_type: str, uuid: str) -> dict[str, Any]:
        """Generic delete operation for a Kea DHCP resource.

        Args:
            api_version: Kea API version segment (``"dhcpv4"`` or ``"dhcpv6"``)
            resource_type: Resource type (e.g., "Subnet", "Reservation")
            uuid: Resource UUID

        Returns:
            Response with 'result' field
        """
        endpoint = f"kea/{api_version}/del{resource_type}/{uuid}"
        return self.client.request("POST", endpoint)

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
            subnet_data: Subnet configuration dictionary with flat
                ``option_data_*`` fields (DHCPv4 wire schema; differs from
                DHCPv6 which nests under ``option_data``):
                - subnet: IPv4 subnet (e.g., "192.168.1.0/24")
                - interface: Interface name (e.g., "opt1")
                - pools: Newline-joined pool ranges
                - description: Operator description
                - option_data_dns_servers: Comma-separated DNS server IPv4 addresses
                - option_data_routers: Comma-separated default-gateway addresses
                - option_data_domain_name: Domain name (string)
                - option_data_ntp_servers: Comma-separated NTP server addresses
                - option_data_domain_search: Comma-separated DNS search domains
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
        return self.client.request("GET", "kea/dhcpv4/get")

    def set_dhcp4_general(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Update Kea DHCPv4 general settings.

        Args:
            settings: General settings to update, wrapped in 'dhcpv4' key.
                Example: {"dhcpv4": {"general": {"enabled": "1", "interfaces": "opt1,opt2"}}}

        Returns:
            Response with 'result' field
        """
        return self.client.request("POST", "kea/dhcpv4/set", data=settings)

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
                - subnet: IPv6 subnet (e.g., "fd00:3742:40:1::/64")
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
        return self.client.request("GET", "kea/dhcpv6/get")

    def set_dhcp6_general(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Update Kea DHCPv6 general settings.

        Args:
            settings: General settings to update, wrapped in 'dhcpv6' key.
                Example: {"dhcpv6": {"enabled": "1", "interfaces": "opt1,opt2"}}

        Returns:
            Response with 'result' field
        """
        return self.client.request("POST", "kea/dhcpv6/set", data=settings)

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
        return self.client.request("POST", "kea/service/reconfigure")


class SystemClient:
    """OPNsense ``<system>`` block API operations (#806).

    Wraps :class:`OPNsenseClient` with one ``get_*_settings`` /
    ``set_*_settings`` pair per ``opnsense.system.*`` singleton surface
    plus the firmware plugin install/lock/remove verbs. Each pair lines
    up with a singleton component manager declared in
    ``OPNsenseProvider.get_direct_api_resource_types()``.

    Endpoint shapes are based on the XML structure of the source box
    (recorded in ``tmp/agents/claude/probe-806.md``) and the standard
    OPNsense REST conventions ``/api/<module>/<controller>/<verb>``. The
    operator should re-verify endpoint shapes via a live probe after the
    cutover.

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

        Returns:
            Raw API response. The wire envelope is typically nested under
            ``{"general": {...}}`` or ``{"system": {"general": {...}}}`` —
            services normalize either shape via ``extract_*_fields``.
        """
        return self.client.request("GET", "system/general/get")

    def set_general_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Update OPNsense system general settings.

        Args:
            settings: Settings payload, typically wrapped in a ``general``
                or ``system.general`` envelope (matches the GET shape).

        Returns:
            Response with ``result`` field (e.g., ``"saved"``).
        """
        return self.client.request("POST", "system/general/set", data=settings)

    # ------------------------------------------------------------------
    # system.ssh / system.webgui (shared system/settings controller)
    # ------------------------------------------------------------------

    def get_system_settings(self) -> dict[str, Any]:
        """Fetch the OPNsense system settings (ssh + webgui subkeys).

        Returns:
            Raw API response. Subkeys ``ssh`` and ``webgui`` are read by
            the per-surface services.
        """
        return self.client.request("GET", "system/settings/get")

    def set_system_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Update OPNsense system settings.

        Args:
            settings: Payload for the ssh/webgui sub-blocks. The caller is
                responsible for wrapping under the correct envelope.

        Returns:
            Response with ``result`` field.
        """
        return self.client.request("POST", "system/settings/set", data=settings)

    # ------------------------------------------------------------------
    # system.firmware
    # ------------------------------------------------------------------

    def get_firmware_info(self) -> dict[str, Any]:
        """Fetch firmware/plugin info: version + installed plugins/packages.

        Returns:
            Raw API response. Notable fields:
            - ``plugin``: list of installed/known plugins with ``installed`` flag.
            - ``package``: list of installed/known packages.
            - ``product_*``: version metadata.
        """
        return self.client.request("GET", "firmware/info")

    def install_plugin(self, name: str) -> dict[str, Any]:
        """Install a single OPNsense plugin (e.g., ``os-acme-client``).

        Args:
            name: Plugin name. Usually starts with ``os-`` for community
                / contrib plugins.

        Returns:
            API response (typically a job-acknowledgement payload).
        """
        return self.client.request("POST", f"firmware/install/{name}")

    def remove_plugin(self, name: str) -> dict[str, Any]:
        """Remove an OPNsense plugin.

        Provided for symmetry with ``install_plugin``; the apply-path of
        :class:`SystemFirmwareManager` does **NOT** call this — extras
        are warned about, not removed (operator decision per #806).

        Args:
            name: Plugin name to remove.

        Returns:
            API response.
        """
        return self.client.request("POST", f"firmware/remove/{name}")

    def lock_plugin(self, name: str) -> dict[str, Any]:
        """Pin a plugin to its current version (no auto-upgrade).

        Args:
            name: Plugin name to lock.

        Returns:
            API response.
        """
        return self.client.request("POST", f"firmware/lock/{name}")

    # ------------------------------------------------------------------
    # system.remotebackup (gdrivebackup MVC)
    # ------------------------------------------------------------------

    def get_remotebackup_settings(self) -> dict[str, Any]:
        """Fetch OPNsense remote-backup (Google Drive) settings.

        Returns:
            Raw API response. The wire envelope is typically
            ``{"gdrivebackup": {"general": {...}}}`` (modern MVC) or
            ``{"general": {...}}`` — services normalize either shape.
        """
        return self.client.request("GET", "gdrivebackup/settings/get")

    def set_remotebackup_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Update OPNsense remote-backup (Google Drive) settings.

        Args:
            settings: Payload (envelope matches the GET shape).

        Returns:
            Response with ``result`` field.
        """
        return self.client.request("POST", "gdrivebackup/settings/set", data=settings)

    # ------------------------------------------------------------------
    # system.tuning (sysctl tunables)
    # ------------------------------------------------------------------

    def get_tuning_settings(self) -> dict[str, Any]:
        """Fetch OPNsense system-tuning (sysctl) settings.

        Returns:
            Raw API response. The MVC ``sysctl`` controller exposes
            ``get`` for the current ``items`` collection.
        """
        return self.client.request("GET", "diagnostics/system/sysctl/get")

    def set_tuning_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Update OPNsense system-tuning (sysctl) settings.

        Args:
            settings: Payload of sysctl items to set.

        Returns:
            Response with ``result`` field.
        """
        return self.client.request("POST", "diagnostics/system/sysctl/set", data=settings)


class RadvdClient:
    """OPNsense ``radvd`` (IPv6 Router Advertisement) MVC API operations (#788).

    Wraps :class:`OPNsenseClient` with the per-entry CRUD verbs the modern
    radvd controller exposes. Endpoint shapes verified live against
    ``opnsense-a`` (2026-05-10 probe captured in
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
        response = self.client.request("POST", "radvd/settings/searchEntry")
        return cast(list[dict[str, Any]], response.get("rows", []))

    def get_record(self, uuid: str) -> dict[str, Any]:
        """Fetch a specific radvd entry by UUID.

        Args:
            uuid: Entry UUID.

        Returns:
            Entry configuration dictionary (wire envelope).
        """
        return self.client.request("GET", f"radvd/settings/getEntry/{uuid}")

    def add_record(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a new radvd entry.

        Args:
            payload: Wire payload wrapped under ``"entry"``.

        Returns:
            API response (typically ``{"result": "saved", "uuid": "..."}``).
        """
        return self.client.request("POST", "radvd/settings/addEntry", data=payload)

    def set_record(self, uuid: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Update an existing radvd entry.

        Args:
            uuid: Entry UUID.
            payload: Wire payload wrapped under ``"entry"``.

        Returns:
            API response (typically ``{"result": "saved"}``).
        """
        return self.client.request("POST", f"radvd/settings/setEntry/{uuid}", data=payload)

    def del_record(self, uuid: str) -> dict[str, Any]:
        """Delete a radvd entry.

        Args:
            uuid: Entry UUID.

        Returns:
            API response.
        """
        return self.client.request("POST", f"radvd/settings/delEntry/{uuid}")

    def reconfigure(self) -> dict[str, Any]:
        """Reconfigure the radvd daemon to apply pending changes.

        Returns:
            API response (typically ``{"status": "ok"}``).
        """
        return self.client.request("POST", "radvd/service/reconfigure")

    def get_service_status(self) -> dict[str, Any]:
        """Fetch radvd daemon status.

        Returns:
            API response (typically ``{"status": "running" | "stopped" | "unknown"}``).
        """
        return self.client.request("GET", "radvd/service/status")

    def get_settings(self) -> dict[str, Any]:
        """Bulk read of all radvd entries via the settings/get endpoint.

        Returns:
            ``{"radvd": {"entries": [...]}}`` envelope.
        """
        return self.client.request("GET", "radvd/settings/get")


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

    _SEARCH = "cron/settings/searchJobs"
    _GET = "cron/settings/getJob/{uuid}"
    _ADD = "cron/settings/addJob"
    _SET = "cron/settings/setJob/{uuid}"
    _DEL = "cron/settings/delJob/{uuid}"
    _RECONFIGURE = "cron/service/reconfigure"

    def __init__(self, client: OPNsenseClient) -> None:
        """Initialize CronClient with an OPNsense client wrapper."""
        self.client = client

    def search_jobs(self) -> list[dict[str, Any]]:
        """Search for all scheduled cron jobs.

        Returns:
            List of job dictionaries (each carrying ``uuid`` plus the
            wire schema fields). Empty list when no jobs exist.
        """
        response = self.client.request("POST", self._SEARCH)
        return cast(list[dict[str, Any]], response.get("rows", []))

    def get_job(self, uuid: str) -> dict[str, Any]:
        """Fetch a specific cron job by UUID.

        Args:
            uuid: Job UUID.

        Returns:
            Job configuration dictionary (wire envelope).
        """
        return self.client.request("GET", self._GET.format(uuid=uuid))

    def add_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a new cron job.

        Args:
            payload: Wire payload wrapped under ``"job"``.

        Returns:
            API response (typically ``{"result": "saved", "uuid": "..."}``).
        """
        return self.client.request("POST", self._ADD, data=payload)

    def set_job(self, uuid: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Update an existing cron job.

        Args:
            uuid: Job UUID.
            payload: Wire payload wrapped under ``"job"``.

        Returns:
            API response (typically ``{"result": "saved"}``).
        """
        return self.client.request("POST", self._SET.format(uuid=uuid), data=payload)

    def del_job(self, uuid: str) -> dict[str, Any]:
        """Delete a cron job.

        Args:
            uuid: Job UUID.

        Returns:
            API response.
        """
        return self.client.request("POST", self._DEL.format(uuid=uuid))

    def reconfigure(self) -> dict[str, Any]:
        """Reconfigure the cron service to apply pending changes.

        Returns:
            API response (typically ``{"status": "ok"}``).
        """
        return self.client.request("POST", self._RECONFIGURE)
