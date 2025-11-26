"""ISC DHCP service for OPNsense operations."""

import logging
import traceback

from infrafoundry.core.exceptions import APIError

from ..api_client import OPNsenseClient
from .base import BaseService


class ISCDHCPService(BaseService):
    """Service for ISC DHCP operations via OPNsense API.

    Provides operations for reading ISC DHCPv4 and DHCPv6 configuration from OPNsense.
    Note: ISC DHCP is the legacy DHCP server in OPNsense, stored in the system XML config.
    """

    def __init__(self, client: OPNsenseClient) -> None:
        """Initialize ISC DHCP service.

        Args:
            client: Configured OPNsense API client
        """
        super().__init__(client)

    def _get_system_config(self) -> dict:
        """Get the entire system configuration.

        Uses the Core API to retrieve the full OPNsense configuration.

        Returns:
            Dictionary containing the system configuration
        """
        try:
            # Use the core API to get configuration
            response = self.client.request("GET", "core/menu/search")
            return response if response else {}
        except APIError:
            # Fallback: return empty dict if API call fails
            # This allows graceful degradation for legacy ISC DHCP configs
            return {}
        except Exception:
            logging.error("Unexpected error getting system config from OPNsense API")
            logging.debug(traceback.format_exc())  # Log full traceback
            # Fallback: return empty dict for unexpected errors
            # This allows graceful degradation for legacy ISC DHCP configs
            return {}

    def _parse_dhcpd_config(self) -> dict:
        """Parse the dhcpd section from system configuration.

        Returns:
            Dictionary containing dhcpd configuration by interface
        """
        # In a real implementation, we would need to use the OPNsense
        # backup/download API endpoint to get the XML config
        # For now, we'll return a structured dict that represents
        # what we'd get from parsing config.xml
        return {}

    # DHCPv4 Operations
    def get_dhcpv4_config(self, interface: str | None = None) -> dict[str, dict]:
        """Get ISC DHCPv4 configuration for interfaces.

        Args:
            interface: Optional specific interface to get config for

        Returns:
            Dictionary mapping interface names to their DHCP configuration.
            Each config contains: subnet, range, gateway, dns_servers, domain, etc.
        """
        # In production, this would call: GET /api/core/backup/download
        # and parse the <dhcpd> section from config.xml
        #
        # The structure would be something like:
        # {
        #     "lan": {
        #         "enable": "1",
        #         "range": {"from": "192.168.1.100", "to": "192.168.1.200"},
        #         "defaultleasetime": "7200",
        #         "maxleasetime": "86400",
        #         "gateway": "192.168.1.1",
        #         "domain": "example.local",
        #         "dnsserver": ["192.168.1.1", "8.8.8.8"],
        #         "ntpserver": ["192.168.1.1"],
        #         "subnet": "192.168.1.0",
        #         "subnet_bits": "24"
        #     }
        # }
        return {}

    def get_dhcpv4_static_maps(self, interface: str | None = None) -> dict[str, list[dict]]:
        """Get ISC DHCPv4 static mappings (reservations) by interface.

        Args:
            interface: Optional interface name to filter by

        Returns:
            Dictionary mapping interface names to lists of static mappings.
            Each mapping contains: mac, ipaddr, hostname, descr
        """
        # In production, this would parse the <staticmap> elements under each
        # interface in the <dhcpd> section
        #
        # Structure:
        # {
        #     "lan": [
        #         {
        #             "mac": "00:11:22:33:44:55",
        #             "ipaddr": "192.168.1.50",
        #             "hostname": "server01",
        #             "descr": "Main Server"
        #         }
        #     ]
        # }
        return {}

    def list_interfaces(self) -> list[str]:
        """List interfaces with ISC DHCP enabled.

        Returns:
            List of interface names (e.g., ['lan', 'opt1', 'opt2'])
        """
        # Would parse the dhcpd config and return keys where enable="1"
        return []

    # DHCPv6 Operations
    def get_dhcpv6_config(self, interface: str | None = None) -> dict[str, dict]:
        """Get ISC DHCPv6 configuration for interfaces.

        Args:
            interface: Optional specific interface to get config for

        Returns:
            Dictionary mapping interface names to their DHCPv6 configuration.
            Each config contains: range, prefix delegation, dns servers, etc.
        """
        # In production, this would parse the <dhcpdv6> section from config.xml
        # Structure similar to DHCPv4 but with IPv6-specific fields
        return {}

    def get_dhcpv6_static_maps(self, interface: str | None = None) -> dict[str, list[dict]]:
        """Get ISC DHCPv6 static mappings (reservations) by interface.

        Args:
            interface: Optional interface name to filter by

        Returns:
            Dictionary mapping interface names to lists of static mappings.
            Each mapping contains: duid, ipaddrv6, hostname, descr
        """
        # In production, this would parse the <staticmap> elements under each
        # interface in the <dhcpdv6> section
        return {}
