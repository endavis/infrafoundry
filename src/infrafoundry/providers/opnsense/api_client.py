"""OPNsense API client for Kea DHCP operations.

This module provides a minimal API client for interacting with OPNsense's Kea DHCP
API endpoints. The implementation is inspired by turnbros/python-opnsense but kept
minimal to avoid unnecessary dependencies.

References:
- https://github.com/turnbros/python-opnsense (Apache 2.0 License)
- OPNsense API: https://docs.opnsense.org/development/api.html
"""

import json
import logging
from base64 import b64encode
from typing import Any, cast

import requests

from infrafoundry.core.exceptions import APIError, AuthenticationError

logger = logging.getLogger(__name__)


class OPNsenseClient:
    """Minimal OPNsense API client for authenticated requests.

    This class handles authentication and HTTP communication with an OPNsense
    firewall API. It follows the pattern from turnbros/python-opnsense but
    uses the requests library for better maintainability.

    Args:
        api_key: OPNsense API key
        api_secret: OPNsense API secret
        base_url: Base URL of OPNsense instance (e.g., https://192.168.1.1)
        verify_ssl: Whether to verify SSL certificates (default: True)
        timeout: Request timeout in seconds (default: 30)

    Example:
        >>> client = OPNsenseClient(
        ...     api_key="your_key",
        ...     api_secret="your_secret",
        ...     base_url="https://opnsense.example.com"
        ... )
        >>> response = client.request("GET", "kea/dhcpv6/searchSubnet")
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        base_url: str,
        verify_ssl: bool = True,
        timeout: int = 30,
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url.rstrip("/")
        self.verify_ssl = verify_ssl
        self.timeout = timeout

        # Create basic auth header
        credentials = f"{api_key}:{api_secret}"
        self.auth_header = b64encode(credentials.encode()).decode("ascii")

    def request(
        self,
        method: str,
        endpoint: str,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an authenticated API request.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path (e.g., "kea/dhcpv6/addSubnet")
            data: Request body data (for POST requests)
            params: URL query parameters

        Returns:
            API response as dictionary

        Raises:
            requests.HTTPError: If the request fails
            ValueError: If the response is not valid JSON
        """
        url = f"{self.base_url}/api/{endpoint}"

        headers = {
            "Authorization": f"Basic {self.auth_header}",
        }

        # Only add Content-Type for requests with data
        if data:
            headers["Content-Type"] = "application/json"

        logger.debug(f"{method} {url}")
        if data:
            logger.debug(f"Request data: {json.dumps(data, indent=2)}")

        try:
            # Build request kwargs
            request_kwargs = {
                "method": method,
                "url": url,
                "headers": headers,
                "params": params,
                "verify": self.verify_ssl,
                "timeout": self.timeout,
            }

            # Only add json parameter if we have data
            if data:
                request_kwargs["json"] = data

            response = requests.request(**request_kwargs)
            response.raise_for_status()

            result = cast(dict[str, Any], response.json())
            logger.debug(f"Response: {json.dumps(result, indent=2)}")
            return result

        except requests.HTTPError as e:
            logger.error(f"HTTP error: {e}")
            status_code = e.response.status_code if hasattr(e, "response") and e.response else None
            response_text = e.response.text if hasattr(e, "response") and e.response else str(e)

            if status_code == 401 or status_code == 403:
                raise AuthenticationError(
                    "OPNsense authentication failed",
                    status_code=status_code,
                    response=response_text,
                    provider="opnsense",
                ) from e
            else:
                raise APIError(
                    f"OPNsense API request failed: {e}",
                    status_code=status_code,
                    response=response_text,
                    provider="opnsense",
                ) from e
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response: {e}")
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

    # DHCPv6 Subnet operations

    def search_dhcp6_subnets(self) -> list[dict[str, Any]]:
        """Search for all DHCPv6 subnets.

        Returns:
            List of subnet dictionaries with 'uuid', 'subnet', 'interface', etc.
        """
        response = self.client.request("GET", "kea/dhcpv6/searchSubnet")
        return cast(list[dict[str, Any]], response.get("rows", []))

    def get_dhcp6_subnet(self, uuid: str) -> dict[str, Any]:
        """Get a specific DHCPv6 subnet by UUID.

        Args:
            uuid: Subnet UUID

        Returns:
            Subnet configuration dictionary
        """
        return self.client.request("GET", f"kea/dhcpv6/getSubnet/{uuid}")

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
        # Wrap data in expected format
        request_data = {"subnet": subnet_data}
        return self.client.request("POST", "kea/dhcpv6/addSubnet", data=request_data)

    def update_dhcp6_subnet(self, uuid: str, subnet_data: dict[str, Any]) -> dict[str, Any]:
        """Update an existing DHCPv6 subnet.

        Args:
            uuid: Subnet UUID
            subnet_data: Updated subnet configuration

        Returns:
            Response with 'result' field
        """
        request_data = {"subnet": subnet_data}
        return self.client.request("POST", f"kea/dhcpv6/setSubnet/{uuid}", data=request_data)

    def delete_dhcp6_subnet(self, uuid: str) -> dict[str, Any]:
        """Delete a DHCPv6 subnet.

        Args:
            uuid: Subnet UUID

        Returns:
            Response with 'result' field
        """
        return self.client.request("POST", f"kea/dhcpv6/delSubnet/{uuid}")

    # DHCPv6 Reservation operations

    def search_dhcp6_reservations(self) -> list[dict[str, Any]]:
        """Search for all DHCPv6 reservations.

        Returns:
            List of reservation dictionaries with 'uuid', 'subnet_id', 'duid', etc.
        """
        response = self.client.request("GET", "kea/dhcpv6/searchReservation")
        return cast(list[dict[str, Any]], response.get("rows", []))

    def get_dhcp6_reservation(self, uuid: str) -> dict[str, Any]:
        """Get a specific DHCPv6 reservation by UUID.

        Args:
            uuid: Reservation UUID

        Returns:
            Reservation configuration dictionary
        """
        return self.client.request("GET", f"kea/dhcpv6/getReservation/{uuid}")

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
        request_data = {"reservation": reservation_data}
        return self.client.request("POST", "kea/dhcpv6/addReservation", data=request_data)

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
        request_data = {"reservation": reservation_data}
        return self.client.request("POST", f"kea/dhcpv6/setReservation/{uuid}", data=request_data)

    def delete_dhcp6_reservation(self, uuid: str) -> dict[str, Any]:
        """Delete a DHCPv6 reservation.

        Args:
            uuid: Reservation UUID

        Returns:
            Response with 'result' field
        """
        return self.client.request("POST", f"kea/dhcpv6/delReservation/{uuid}")

    # Service operations

    def reconfigure_service(self) -> dict[str, Any]:
        """Reconfigure the Kea service to apply changes.

        This should be called after adding, updating, or deleting subnets
        or reservations to activate the changes.

        Returns:
            Response with 'status' field (should be 'ok')
        """
        return self.client.request("POST", "kea/service/reconfigure")
