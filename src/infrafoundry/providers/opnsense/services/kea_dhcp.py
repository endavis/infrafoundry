"""Kea DHCP service for OPNsense operations."""

import yaml

from ..api_client import KeaClient, OPNsenseClient
from .base import BaseService


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
    def search_dhcpv4_reservations(self) -> list[dict]:
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

    def search_dhcpv4_subnets(self) -> list[dict]:
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
    def search_dhcpv6_reservations(self) -> list[dict]:
        """Search for all DHCPv6 reservations.

        Returns:
            List of reservation dictionaries
        """
        return self.kea_client.search_dhcp6_reservations()

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

    def search_dhcpv6_subnets(self) -> list[dict]:
        """Search for all DHCPv6 subnets.

        Returns:
            List of subnet dictionaries
        """
        return self.kea_client.search_dhcp6_subnets()

    def delete_dhcpv6_subnet(self, uuid: str) -> None:
        """Delete a DHCPv6 subnet by UUID.

        Args:
            uuid: Subnet UUID
        """
        self.kea_client.delete_dhcp6_subnet(uuid)

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
