"""ISC to Kea DHCP migration component manager."""

from __future__ import annotations

from typing import Any, cast

from ..services.isc_dhcp import ISCDHCPService
from .base import BaseComponentManager
from contextlib import suppress


class _BaseDHCPConverter:
    """Shared helpers for converting ISC DHCP config to Kea resources."""

    subnet_suffix = ""

    def convert_subnet(self, interface: str, isc_config: dict[str, Any]) -> dict[str, Any] | None:
        if not self._is_enabled(isc_config):
            return None

        subnet_cidr = self._subnet_cidr(isc_config)
        if not subnet_cidr:
            return None

        kea_config: dict[str, Any] = {
            "subnet": subnet_cidr,
            "interface": interface,
            "pools": self._build_pools(isc_config),
        }
        kea_config.update(self._common_subnet_fields(isc_config))
        kea_config.update(self._version_specific_subnet_fields(isc_config))

        return {
            "name": f"{interface}{self.subnet_suffix}",
            "config": kea_config,
        }

    def convert_reservation(
        self,
        interface: str,
        static_map: dict[str, Any],
        subnet_config: dict[str, Any],
    ) -> dict[str, Any] | None:
        identifier = self._reservation_identifier(static_map)
        address = self._reservation_address(static_map)
        if not identifier or not address:
            return None

        subnet_cidr = self._reservation_subnet(subnet_config, static_map, address)
        if not subnet_cidr:
            return None

        kea_config = {"subnet": subnet_cidr}
        kea_config.update(self._reservation_core_fields(identifier, address))
        kea_config.update(self._reservation_extra_fields(static_map))

        name = self._reservation_name(interface, static_map, identifier)
        return {"name": name, "config": kea_config}

    def _is_enabled(self, isc_config: dict[str, Any]) -> bool:
        return isc_config.get("enable") == "1"

    def _build_pools(self, isc_config: dict[str, Any]) -> list[dict[str, str]]:
        pools: list[dict[str, str]] = []
        range_config = isc_config.get("range")
        if isinstance(range_config, dict):
            range_from = range_config.get("from")
            range_to = range_config.get("to")
            if range_from and range_to:
                pools.append({"range": f"{range_from} - {range_to}"})
        return pools

    def _common_subnet_fields(self, isc_config: dict[str, Any]) -> dict[str, Any]:
        fields: dict[str, Any] = {}

        dns_servers = self._as_list(isc_config.get("dnsserver"))
        if dns_servers:
            fields["dns_servers"] = dns_servers

        if "defaultleasetime" in isc_config:
            with suppress(TypeError, ValueError):
                fields["valid_lifetime"] = int(isc_config["defaultleasetime"])
 
        if "maxleasetime" in isc_config:
            with suppress(TypeError, ValueError):
                fields["max_lifetime"] = int(isc_config["maxleasetime"])

        return fields

    def _as_list(self, value: Any) -> list[Any]:
        if value is None or value == "":
            return []
        if isinstance(value, list):
            return [item for item in value if item not in (None, "")]
        return [value]

    def _subnet_cidr(self, isc_config: dict[str, Any]) -> str | None:
        raise NotImplementedError

    def _version_specific_subnet_fields(self, isc_config: dict[str, Any]) -> dict[str, Any]:
        return {}

    def _reservation_identifier(self, static_map: dict[str, Any]) -> str | None:
        raise NotImplementedError

    def _reservation_address(self, static_map: dict[str, Any]) -> str | None:
        raise NotImplementedError

    def _reservation_core_fields(self, identifier: str, address: str) -> dict[str, Any]:
        raise NotImplementedError

    def _reservation_extra_fields(self, static_map: dict[str, Any]) -> dict[str, Any]:
        return {}

    def _reservation_name(
        self,
        interface: str,
        static_map: dict[str, Any],
        identifier: str,
    ) -> str:
        raise NotImplementedError

    def _reservation_subnet(
        self,
        subnet_config: dict[str, Any],
        static_map: dict[str, Any],
        address: str,
    ) -> str | None:
        return self._subnet_cidr(subnet_config)


class _DHCPv4Converter(_BaseDHCPConverter):
    subnet_suffix = "-dhcp"

    def _subnet_cidr(self, isc_config: dict[str, Any]) -> str | None:
        subnet = isc_config.get("subnet")
        if not subnet:
            return None
        subnet_bits = isc_config.get("subnet_bits", "24")
        return f"{subnet}/{subnet_bits}"

    def _version_specific_subnet_fields(self, isc_config: dict[str, Any]) -> dict[str, Any]:
        fields: dict[str, Any] = {}
        if gateway := isc_config.get("gateway"):
            fields["router"] = gateway
        if domain := isc_config.get("domain"):
            fields["domain"] = domain
        ntp_servers = self._as_list(isc_config.get("ntpserver"))
        if ntp_servers:
            fields["ntp_servers"] = ntp_servers
        return fields

    def _reservation_identifier(self, static_map: dict[str, Any]) -> str | None:
        return static_map.get("mac")

    def _reservation_address(self, static_map: dict[str, Any]) -> str | None:
        return static_map.get("ipaddr")

    def _reservation_core_fields(self, identifier: str, address: str) -> dict[str, Any]:
        return {"hw_address": identifier, "ip_address": address}

    def _reservation_extra_fields(self, static_map: dict[str, Any]) -> dict[str, Any]:
        fields: dict[str, Any] = {}
        if hostname := static_map.get("hostname"):
            fields["hostname"] = hostname
        if description := static_map.get("descr"):
            fields["description"] = description
        return fields

    def _reservation_name(
        self,
        interface: str,
        static_map: dict[str, Any],
        identifier: str,
    ) -> str:
        hostname = static_map.get("hostname")
        if hostname:
            return cast(str, hostname)
        compact_mac = identifier.replace(":", "")
        return f"{interface}-{compact_mac[:8]}"


class _DHCPv6Converter(_BaseDHCPConverter):
    subnet_suffix = "-dhcpv6"

    def _prefix_length(self, isc_config: dict[str, Any]) -> str:
        prefix_range = isc_config.get("prefixrange", {}) or {}
        return cast(str, prefix_range.get("prefixlength", "64"))

    def _subnet_cidr(self, isc_config: dict[str, Any]) -> str | None:
        subnet = isc_config.get("subnet")
        if not subnet:
            return None
        prefix_length = self._prefix_length(isc_config)
        return f"{subnet}/{prefix_length}"

    def _version_specific_subnet_fields(self, isc_config: dict[str, Any]) -> dict[str, Any]:
        fields: dict[str, Any] = {}

        domain = isc_config.get("domain")
        domain_search = self._as_list(isc_config.get("domainsearchlist"))
        if domain_search:
            fields["dns_search_list"] = domain_search
        elif domain:
            fields["dns_search_list"] = [domain]

        if description := isc_config.get("descr"):
            fields["description"] = description

        return fields

    def _reservation_identifier(self, static_map: dict[str, Any]) -> str | None:
        return static_map.get("duid")

    def _reservation_address(self, static_map: dict[str, Any]) -> str | None:
        return static_map.get("ipaddrv6")

    def _reservation_core_fields(self, identifier: str, address: str) -> dict[str, Any]:
        return {"duid": identifier, "ip_address": address}

    def _reservation_extra_fields(self, static_map: dict[str, Any]) -> dict[str, Any]:
        fields: dict[str, Any] = {}
        if hostname := static_map.get("hostname"):
            fields["hostname"] = hostname
        if description := static_map.get("descr"):
            fields["description"] = description
        return fields

    def _reservation_name(
        self,
        interface: str,
        static_map: dict[str, Any],
        identifier: str,
    ) -> str:
        hostname = static_map.get("hostname")
        if hostname:
            return cast(str, hostname)
        return f"{interface}-{identifier[:16]}"

    def _reservation_subnet(
        self,
        subnet_config: dict[str, Any],
        static_map: dict[str, Any],
        address: str,
    ) -> str | None:
        subnet_cidr = self._subnet_cidr(subnet_config)
        if subnet_cidr:
            return subnet_cidr

        prefix_length = self._prefix_length(subnet_config)
        if ":" in address:
            network_prefix = address.rsplit(":", 1)[0]
            return f"{network_prefix}::/{prefix_length}"
        return f"{address}/{prefix_length}"


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
        return self._migrate_dhcp(
            env_name=env_name,
            provider_name=provider_name,
            interfaces=interfaces,
            converter=_DHCPv4Converter(),
            config_attr="get_dhcpv4_config",
            static_attr="get_dhcpv4_static_maps",
        )

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
        return self._migrate_dhcp(
            env_name=env_name,
            provider_name=provider_name,
            interfaces=interfaces,
            converter=_DHCPv6Converter(),
            config_attr="get_dhcpv6_config",
            static_attr="get_dhcpv6_static_maps",
        )

    def _migrate_dhcp(
        self,
        env_name: str,
        provider_name: str,
        interfaces: list[str] | None,
        converter: _BaseDHCPConverter,
        *,
        config_attr: str,
        static_attr: str,
    ) -> dict[str, list[dict[str, Any]]]:
        """Shared DHCP migration implementation for v4/v6."""
        isc_service: ISCDHCPService = ISCDHCPService.from_environment(
            env_name, provider_name, self.config_dir
        )

        isc_config = getattr(isc_service, config_attr)()
        static_maps = getattr(isc_service, static_attr)()

        if interfaces:
            interface_set = set(interfaces)
            isc_config = {iface: cfg for iface, cfg in isc_config.items() if iface in interface_set}
            static_maps = {
                iface: maps for iface, maps in static_maps.items() if iface in interface_set
            }

        subnets: list[dict[str, Any]] = []
        reservations: list[dict[str, Any]] = []

        for interface, config in isc_config.items():
            subnet_config = converter.convert_subnet(interface, config)
            if subnet_config:
                subnets.append(subnet_config)

            for static_map in static_maps.get(interface, []):
                reservation_config = converter.convert_reservation(interface, static_map, config)
                if reservation_config:
                    reservations.append(reservation_config)

        return {"subnets": subnets, "reservations": reservations}

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
