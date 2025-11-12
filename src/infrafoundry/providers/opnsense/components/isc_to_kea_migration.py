"""ISC to Kea DHCP migration component manager."""

from ..services.isc_dhcp import ISCDHCPService
from .base import BaseComponentManager


class ISCToKeaMigrationManager(BaseComponentManager):
    """Manager for migrating from ISC DHCP to Kea DHCP.

    Orchestrates the migration process from legacy ISC DHCP to modern Kea DHCP,
    handling both DHCPv4 and DHCPv6 configurations.
    """

    def migrate_dhcpv4(
        self, env_name: str, provider_name: str = "opnsense", interfaces: list[str] | None = None
    ) -> dict[str, list[dict]]:
        """Migrate ISC DHCPv4 configuration to Kea DHCPv4.

        Reads the ISC DHCPv4 configuration and generates equivalent Kea DHCP
        resources (subnets and reservations).

        Args:
            env_name: Environment name
            provider_name: Provider name (defaults to 'opnsense')
            interfaces: List of interfaces to migrate (None = all)

        Returns:
            Dictionary with 'subnets' and 'reservations' keys containing resource configs
        """
        isc_service: ISCDHCPService = ISCDHCPService.from_environment(  # type: ignore[assignment]
            env_name, provider_name, self.config_dir
        )

        # Get ISC DHCP configuration
        isc_config = isc_service.get_dhcpv4_config()
        static_maps = isc_service.get_dhcpv4_static_maps()

        # Filter interfaces if specified
        if interfaces:
            isc_config = {iface: cfg for iface, cfg in isc_config.items() if iface in interfaces}
            static_maps = {
                iface: maps for iface, maps in static_maps.items() if iface in interfaces
            }

        subnets = []
        reservations = []

        # Transform ISC config to Kea format
        for interface, config in isc_config.items():
            # Convert ISC subnet to Kea subnet
            subnet_config = self._convert_dhcpv4_subnet(interface, config)
            if subnet_config:
                subnets.append(subnet_config)

            # Convert ISC static maps to Kea reservations
            if interface in static_maps:
                for static_map in static_maps[interface]:
                    reservation_config = self._convert_dhcpv4_reservation(
                        interface, static_map, config
                    )
                    if reservation_config:
                        reservations.append(reservation_config)

        return {"subnets": subnets, "reservations": reservations}

    def _convert_dhcpv4_subnet(self, interface: str, isc_config: dict) -> dict | None:
        """Convert ISC DHCPv4 subnet configuration to Kea format.

        Args:
            interface: Interface name (e.g., 'lan', 'opt1')
            isc_config: ISC DHCP configuration dictionary

        Returns:
            Dictionary with 'name' and 'config' keys for Kea subnet, or None if invalid
        """
        # Check if DHCP is enabled (ISC uses "1" for enabled, "0" or missing for disabled)
        enabled = isc_config.get("enable")
        if enabled != "1":
            return None

        # Extract subnet information
        subnet = isc_config.get("subnet")
        subnet_bits = isc_config.get("subnet_bits", "24")

        if not subnet:
            return None

        # Build subnet CIDR
        subnet_cidr = f"{subnet}/{subnet_bits}"

        # Extract pool range
        pools = []
        range_config = isc_config.get("range", {})
        if isinstance(range_config, dict):
            range_from = range_config.get("from")
            range_to = range_config.get("to")
            if range_from and range_to:
                pools.append({"range": f"{range_from} - {range_to}"})

        # Extract DNS servers
        dns_servers = []
        dnsserver = isc_config.get("dnsserver", [])
        if isinstance(dnsserver, list):
            dns_servers = dnsserver
        elif dnsserver:
            dns_servers = [dnsserver]

        # Extract gateway (router option)
        gateway = isc_config.get("gateway")

        # Build Kea subnet configuration
        kea_config = {
            "subnet": subnet_cidr,
            "interface": interface,
            "pools": pools,
        }

        # Add optional fields
        if dns_servers:
            kea_config["dns_servers"] = dns_servers

        if gateway:
            kea_config["router"] = gateway

        if "domain" in isc_config:
            kea_config["domain"] = isc_config["domain"]

        if "defaultleasetime" in isc_config:
            kea_config["valid_lifetime"] = int(isc_config["defaultleasetime"])

        if "maxleasetime" in isc_config:
            kea_config["max_lifetime"] = int(isc_config["maxleasetime"])

        # NTP servers
        if "ntpserver" in isc_config:
            ntp_servers = isc_config["ntpserver"]
            if isinstance(ntp_servers, list):
                kea_config["ntp_servers"] = ntp_servers
            elif ntp_servers:
                kea_config["ntp_servers"] = [ntp_servers]

        return {
            "name": f"{interface}-dhcp",
            "config": kea_config,
        }

    def _convert_dhcpv4_reservation(
        self, interface: str, static_map: dict, subnet_config: dict
    ) -> dict | None:
        """Convert ISC DHCPv4 static mapping to Kea reservation.

        Args:
            interface: Interface name
            static_map: ISC static mapping dictionary
            subnet_config: Parent subnet configuration

        Returns:
            Dictionary with 'name' and 'config' keys for Kea reservation, or None if invalid
        """
        mac = static_map.get("mac")
        ipaddr = static_map.get("ipaddr")
        hostname = static_map.get("hostname", "")

        if not mac or not ipaddr:
            return None

        # Generate subnet reference
        subnet = subnet_config.get("subnet")
        subnet_bits = subnet_config.get("subnet_bits", "24")
        subnet_cidr = f"{subnet}/{subnet_bits}"

        # Build Kea reservation configuration
        kea_config = {
            "subnet": subnet_cidr,
            "hw_address": mac,
            "ip_address": ipaddr,
        }

        if hostname:
            kea_config["hostname"] = hostname

        if "descr" in static_map:
            kea_config["description"] = static_map["descr"]

        # Generate a name for the reservation
        name = hostname if hostname else f"{interface}-{mac.replace(':', '')[:8]}"

        return {
            "name": name,
            "config": kea_config,
        }

    def migrate_dhcpv6(
        self, env_name: str, provider_name: str = "opnsense", interfaces: list[str] | None = None
    ) -> dict[str, list[dict]]:
        """Migrate ISC DHCPv6 configuration to Kea DHCPv6.

        Reads the ISC DHCPv6 configuration and generates equivalent Kea DHCPv6
        resources (subnets and reservations).

        Args:
            env_name: Environment name
            provider_name: Provider name (defaults to 'opnsense')
            interfaces: List of interfaces to migrate (None = all)

        Returns:
            Dictionary with 'subnets' and 'reservations' keys containing resource configs
        """
        isc_service: ISCDHCPService = ISCDHCPService.from_environment(  # type: ignore[assignment]
            env_name, provider_name, self.config_dir
        )

        # Get ISC DHCPv6 configuration
        isc_config = isc_service.get_dhcpv6_config()
        static_maps = isc_service.get_dhcpv6_static_maps()

        # Filter interfaces if specified
        if interfaces:
            isc_config = {iface: cfg for iface, cfg in isc_config.items() if iface in interfaces}
            static_maps = {
                iface: maps for iface, maps in static_maps.items() if iface in interfaces
            }

        subnets = []
        reservations = []

        # Transform ISC config to Kea format
        for interface, config in isc_config.items():
            # Convert ISC subnet to Kea subnet
            subnet_config = self._convert_dhcpv6_subnet(interface, config)
            if subnet_config:
                subnets.append(subnet_config)

            # Convert ISC static maps to Kea reservations
            if interface in static_maps:
                for static_map in static_maps[interface]:
                    reservation_config = self._convert_dhcpv6_reservation(
                        interface, static_map, config
                    )
                    if reservation_config:
                        reservations.append(reservation_config)

        return {"subnets": subnets, "reservations": reservations}

    def _convert_dhcpv6_subnet(self, interface: str, isc_config: dict) -> dict | None:
        """Convert ISC DHCPv6 subnet configuration to Kea format.

        Args:
            interface: Interface name (e.g., 'lan', 'opt1')
            isc_config: ISC DHCPv6 configuration dictionary

        Returns:
            Dictionary with 'name' and 'config' keys for Kea DHCPv6 subnet, or None if invalid
        """
        # Check if DHCPv6 is enabled (ISC uses "1" for enabled, "0" or missing for disabled)
        enabled = isc_config.get("enable")
        if enabled != "1":
            return None

        # Extract subnet/range information
        # DHCPv6 can use range or subnet
        range_config = isc_config.get("range", {})
        subnet = isc_config.get("subnet")

        pools = []
        subnet_cidr = None

        # Handle range-based configuration
        if isinstance(range_config, dict):
            range_from = range_config.get("from")
            range_to = range_config.get("to")
            if range_from and range_to:
                pools.append({"range": f"{range_from} - {range_to}"})
                # Try to derive subnet from range (simplified)
                if subnet:
                    prefix_length = isc_config.get("prefixrange", {}).get("prefixlength", "64")
                    subnet_cidr = f"{subnet}/{prefix_length}"

        # Handle subnet-based configuration
        if not subnet_cidr and subnet:
            prefix_length = isc_config.get("prefixrange", {}).get("prefixlength", "64")
            subnet_cidr = f"{subnet}/{prefix_length}"

        if not subnet_cidr:
            return None

        # Build Kea subnet configuration
        kea_config = {
            "subnet": subnet_cidr,
            "interface": interface,
            "pools": pools,
        }

        # Extract DNS servers
        dns_servers = []
        dnsserver = isc_config.get("dnsserver", [])
        if isinstance(dnsserver, list):
            dns_servers = dnsserver
        elif dnsserver:
            dns_servers = [dnsserver]

        if dns_servers:
            kea_config["dns_servers"] = dns_servers

        # Domain search list
        if "domain" in isc_config:
            kea_config["dns_search_list"] = [isc_config["domain"]]

        if "domainsearchlist" in isc_config:
            search_list = isc_config["domainsearchlist"]
            if isinstance(search_list, list):
                kea_config["dns_search_list"] = search_list
            elif search_list:
                kea_config["dns_search_list"] = [search_list]

        # Lease times
        if "defaultleasetime" in isc_config:
            kea_config["valid_lifetime"] = int(isc_config["defaultleasetime"])

        if "maxleasetime" in isc_config:
            kea_config["max_lifetime"] = int(isc_config["maxleasetime"])

        # Description
        if "descr" in isc_config:
            kea_config["description"] = isc_config["descr"]

        return {
            "name": f"{interface}-dhcpv6",
            "config": kea_config,
        }

    def _convert_dhcpv6_reservation(
        self, interface: str, static_map: dict, subnet_config: dict
    ) -> dict | None:
        """Convert ISC DHCPv6 static mapping to Kea reservation.

        Args:
            interface: Interface name
            static_map: ISC static mapping dictionary
            subnet_config: Parent subnet configuration

        Returns:
            Dictionary with 'name' and 'config' keys for Kea DHCPv6 reservation, or None
        """
        duid = static_map.get("duid")
        ipaddr = static_map.get("ipaddrv6")
        hostname = static_map.get("hostname", "")

        if not duid or not ipaddr:
            return None

        # Generate subnet reference
        subnet = subnet_config.get("subnet")
        prefix_length = subnet_config.get("prefixrange", {}).get("prefixlength", "64")
        if subnet:
            subnet_cidr = f"{subnet}/{prefix_length}"
        else:
            # Fallback: try to derive from IP address
            subnet_cidr = f"{ipaddr.rsplit(':', 1)[0]}::/{prefix_length}"

        # Build Kea reservation configuration
        kea_config = {
            "subnet": subnet_cidr,
            "duid": duid,
            "ip_address": ipaddr,
        }

        if hostname:
            kea_config["hostname"] = hostname

        if "descr" in static_map:
            kea_config["description"] = static_map["descr"]

        # Generate a name for the reservation
        name = hostname if hostname else f"{interface}-{duid[:16]}"

        return {
            "name": name,
            "config": kea_config,
        }

    def migrate_all(
        self, env_name: str, provider_name: str = "opnsense", interfaces: list[str] | None = None
    ) -> dict[str, dict[str, list[dict]]]:
        """Migrate both ISC DHCPv4 and DHCPv6 to Kea.

        Args:
            env_name: Environment name
            provider_name: Provider name (defaults to 'opnsense')
            interfaces: List of interfaces to migrate (None = all)

        Returns:
            Dictionary with 'dhcpv4' and 'dhcpv6' keys, each containing
            'subnets' and 'reservations' lists
        """
        dhcpv4_resources = self.migrate_dhcpv4(env_name, provider_name, interfaces)
        dhcpv6_resources = self.migrate_dhcpv6(env_name, provider_name, interfaces)

        return {"dhcpv4": dhcpv4_resources, "dhcpv6": dhcpv6_resources}

    def export_to_yaml(
        self, env_name: str, provider_name: str = "opnsense", interfaces: list[str] | None = None
    ) -> str:
        """Export migrated configuration as InfraFoundry YAML.

        Args:
            env_name: Environment name
            provider_name: Provider name (defaults to 'opnsense')
            interfaces: List of interfaces to migrate (None = all)

        Returns:
            YAML string containing all migrated resources
        """
        import yaml

        migration_data = self.migrate_all(env_name, provider_name, interfaces)

        resources = []

        # Add DHCPv4 subnets
        for subnet in migration_data["dhcpv4"]["subnets"]:
            resources.append(
                {
                    "provider": "opnsense",
                    "type": "kea_subnet",
                    "name": subnet["name"],
                    "config": subnet["config"],
                }
            )

        # Add DHCPv4 reservations
        for reservation in migration_data["dhcpv4"]["reservations"]:
            resources.append(
                {
                    "provider": "opnsense",
                    "type": "kea_reservation",
                    "name": reservation["name"],
                    "config": reservation["config"],
                }
            )

        # Add DHCPv6 subnets
        for subnet in migration_data["dhcpv6"]["subnets"]:
            resources.append(
                {
                    "provider": "opnsense",
                    "type": "kea_dhcp6_subnet",
                    "name": subnet["name"],
                    "config": subnet["config"],
                }
            )

        # Add DHCPv6 reservations
        for reservation in migration_data["dhcpv6"]["reservations"]:
            resources.append(
                {
                    "provider": "opnsense",
                    "type": "kea_dhcp6_reservation",
                    "name": reservation["name"],
                    "config": reservation["config"],
                }
            )

        config = {"resources": resources}
        return yaml.dump(config, default_flow_style=False, sort_keys=False)
