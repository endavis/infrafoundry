"""Kea DHCP component manager for OPNsense."""

from ..services.kea_dhcp import KeaDHCPService
from .base import BaseComponentManager


class KeaDHCPManager(BaseComponentManager):
    """Manager for Kea DHCP component operations.

    Orchestrates Kea DHCP service operations including reset, migration,
    and configuration management for both DHCPv4 and DHCPv6.
    """

    def reset_dhcpv4(self, env_name: str, provider_name: str = "opnsense") -> None:
        """Reset (delete) all Kea DHCPv4 configuration.

        This removes all Kea DHCPv4 subnets and reservations from OPNsense,
        allowing a fresh configuration to be applied.

        Args:
            env_name: Environment name to reset
            provider_name: Provider name (defaults to 'opnsense')
        """
        service: KeaDHCPService = KeaDHCPService.from_environment(
            env_name, provider_name, self.config_dir
        )

        # Delete all reservations first (they depend on subnets)
        service.delete_all_dhcpv4_reservations()

        # Delete all subnets
        service.delete_all_dhcpv4_subnets()

        # Reconfigure service to apply changes
        service.reconfigure()

    def reset_dhcpv6(self, env_name: str, provider_name: str = "opnsense") -> None:
        """Reset (delete) all Kea DHCPv6 configuration.

        This removes all Kea DHCPv6 subnets and reservations from OPNsense,
        allowing a fresh configuration to be applied.

        Args:
            env_name: Environment name to reset
            provider_name: Provider name (defaults to 'opnsense')
        """
        service: KeaDHCPService = KeaDHCPService.from_environment(
            env_name, provider_name, self.config_dir
        )

        # Delete all reservations first (they depend on subnets)
        service.delete_all_dhcpv6_reservations()

        # Delete all subnets
        service.delete_all_dhcpv6_subnets()

        # Reconfigure service to apply changes
        service.reconfigure()

    def reset_all(self, env_name: str, provider_name: str = "opnsense") -> None:
        """Reset both DHCPv4 and DHCPv6 configurations.

        Args:
            env_name: Environment name to reset
            provider_name: Provider name (defaults to 'opnsense')
        """
        self.reset_dhcpv4(env_name, provider_name)
        self.reset_dhcpv6(env_name, provider_name)

    def migrate(self, env_name: str, provider_name: str = "opnsense") -> str:
        """Migrate current Kea DHCP configuration to InfraFoundry YAML.

        Reads the current Kea DHCPv4 and DHCPv6 configuration from OPNsense
        and generates InfraFoundry-compatible YAML configuration.

        Args:
            env_name: Environment name
            provider_name: Provider name (defaults to 'opnsense')

        Returns:
            YAML configuration as a string
        """
        service: KeaDHCPService = KeaDHCPService.from_environment(
            env_name, provider_name, self.config_dir
        )
        return service.export_to_yaml()
