"""OPNsense API client built on the opnsense-openapi package."""

import json
import logging
from typing import TYPE_CHECKING, Any, cast

import httpx
from opnsense_openapi import OPNsenseClient as OpenAPIOPNsenseClient  # type: ignore[import-untyped]

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
    ) -> None:
        self.client = OpenAPIOPNsenseClient(
            base_url=base_url,
            api_key=api_key,
            api_secret=api_secret,
            verify_ssl=verify_ssl,
            timeout=timeout,
            auto_detect_version=False,
        )

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

            return cast(dict[str, Any], response)

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

    This class provides methods for managing Kea DHCPv6 subnets and reservations
    through the OPNsense API. It wraps the generic OPNsenseClient with domain-
    specific operations.

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

    def _crud_search(self, resource_type: str) -> list[dict[str, Any]]:
        """Generic search operation for Kea DHCPv6 resources.

        Args:
            resource_type: Resource type (e.g., "Subnet", "Reservation")

        Returns:
            List of resource dictionaries from the 'rows' field
        """
        endpoint = f"kea/dhcpv6/search{resource_type}"
        response = self.client.request("GET", endpoint)
        return cast(list[dict[str, Any]], response.get("rows", []))

    def _crud_get(self, resource_type: str, uuid: str) -> dict[str, Any]:
        """Generic get operation for a specific Kea DHCPv6 resource.

        Args:
            resource_type: Resource type (e.g., "Subnet", "Reservation")
            uuid: Resource UUID

        Returns:
            Resource configuration dictionary
        """
        endpoint = f"kea/dhcpv6/get{resource_type}/{uuid}"
        return self.client.request("GET", endpoint)

    def _crud_add(
        self, resource_type: str, resource_key: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        """Generic add operation for a new Kea DHCPv6 resource.

        Args:
            resource_type: Resource type (e.g., "Subnet", "Reservation")
            resource_key: Key to wrap data in request (e.g., "subnet", "reservation")
            data: Resource configuration

        Returns:
            Response with 'result' and 'uuid' fields
        """
        endpoint = f"kea/dhcpv6/add{resource_type}"
        request_data = {resource_key: data}
        return self.client.request("POST", endpoint, data=request_data)

    def _crud_update(
        self, resource_type: str, uuid: str, resource_key: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        """Generic update operation for an existing Kea DHCPv6 resource.

        Args:
            resource_type: Resource type (e.g., "Subnet", "Reservation")
            uuid: Resource UUID
            resource_key: Key to wrap data in request (e.g., "subnet", "reservation")
            data: Updated resource configuration

        Returns:
            Response with 'result' field
        """
        endpoint = f"kea/dhcpv6/set{resource_type}/{uuid}"
        request_data = {resource_key: data}
        return self.client.request("POST", endpoint, data=request_data)

    def _crud_delete(self, resource_type: str, uuid: str) -> dict[str, Any]:
        """Generic delete operation for a Kea DHCPv6 resource.

        Args:
            resource_type: Resource type (e.g., "Subnet", "Reservation")
            uuid: Resource UUID

        Returns:
            Response with 'result' field
        """
        endpoint = f"kea/dhcpv6/del{resource_type}/{uuid}"
        return self.client.request("POST", endpoint)

    # DHCPv6 Subnet operations

    def search_dhcp6_subnets(self) -> list[dict[str, Any]]:
        """Search for all DHCPv6 subnets.

        Returns:
            List of subnet dictionaries with 'uuid', 'subnet', 'interface', etc.
        """
        return self._crud_search("Subnet")

    def get_dhcp6_subnet(self, uuid: str) -> dict[str, Any]:
        """Get a specific DHCPv6 subnet by UUID.

        Args:
            uuid: Subnet UUID

        Returns:
            Subnet configuration dictionary
        """
        return self._crud_get("Subnet", uuid)

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
        return self._crud_add("Subnet", "subnet", subnet_data)

    def update_dhcp6_subnet(self, uuid: str, subnet_data: dict[str, Any]) -> dict[str, Any]:
        """Update an existing DHCPv6 subnet.

        Args:
            uuid: Subnet UUID
            subnet_data: Updated subnet configuration

        Returns:
            Response with 'result' field
        """
        return self._crud_update("Subnet", uuid, "subnet", subnet_data)

    def delete_dhcp6_subnet(self, uuid: str) -> dict[str, Any]:
        """Delete a DHCPv6 subnet.

        Args:
            uuid: Subnet UUID

        Returns:
            Response with 'result' field
        """
        return self._crud_delete("Subnet", uuid)

    # DHCPv6 Reservation operations

    def search_dhcp6_reservations(self) -> list[dict[str, Any]]:
        """Search for all DHCPv6 reservations.

        Returns:
            List of reservation dictionaries with 'uuid', 'subnet_id', 'duid', etc.
        """
        return self._crud_search("Reservation")

    def get_dhcp6_reservation(self, uuid: str) -> dict[str, Any]:
        """Get a specific DHCPv6 reservation by UUID.

        Args:
            uuid: Reservation UUID

        Returns:
            Reservation configuration dictionary
        """
        return self._crud_get("Reservation", uuid)

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
        return self._crud_add("Reservation", "reservation", reservation_data)

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
        return self._crud_update("Reservation", uuid, "reservation", reservation_data)

    def delete_dhcp6_reservation(self, uuid: str) -> dict[str, Any]:
        """Delete a DHCPv6 reservation.

        Args:
            uuid: Reservation UUID

        Returns:
            Response with 'result' field
        """
        return self._crud_delete("Reservation", uuid)

    # Service operations

    def reconfigure_service(self) -> dict[str, Any]:
        """Reconfigure the Kea service to apply changes.

        This should be called after adding, updating, or deleting subnets
        or reservations to activate the changes.

        Returns:
            Response with 'status' field (should be 'ok')
        """
        return self.client.request("POST", "kea/service/reconfigure")
