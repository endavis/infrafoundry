"""Tests for ISC to Kea DHCP migration."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.providers.opnsense.components.isc_to_kea_migration import (
    ISCToKeaMigrationManager,
)


class TestISCToKeaMigration:
    """Test ISC to Kea DHCP migration functionality."""

    @pytest.fixture
    def manager(self, tmp_path: Path) -> ISCToKeaMigrationManager:
        """Create a migration manager instance."""
        return ISCToKeaMigrationManager(tmp_path)

    @pytest.fixture
    def mock_isc_service(self):
        """Create a mock ISC DHCP service."""
        mock = MagicMock()
        mock.get_dhcpv4_config.return_value = {
            "lan": {
                "enable": "1",
                "subnet": "192.168.1.0",
                "subnet_bits": "24",
                "range": {"from": "192.168.1.100", "to": "192.168.1.200"},
                "gateway": "192.168.1.1",
                "domain": "example.local",
                "dnsserver": ["192.168.1.1", "8.8.8.8"],
                "ntpserver": ["192.168.1.1"],
                "defaultleasetime": "7200",
                "maxleasetime": "86400",
            }
        }
        mock.get_dhcpv4_static_maps.return_value = {
            "lan": [
                {
                    "mac": "00:11:22:33:44:55",
                    "ipaddr": "192.168.1.50",
                    "hostname": "server01",
                    "descr": "Main Server",
                }
            ]
        }
        mock.get_dhcpv6_config.return_value = {
            "lan": {
                "enable": "1",
                "subnet": "fd00::",
                "prefixrange": {"prefixlength": "64"},
                "range": {"from": "fd00::1000", "to": "fd00::2000"},
                "dnsserver": ["fd00::1"],
                "domain": "example.local",
                "defaultleasetime": "7200",
            }
        }
        mock.get_dhcpv6_static_maps.return_value = {
            "lan": [
                {
                    "duid": "00:01:00:01:12:34:56:78:00:11:22:33:44:55",
                    "ipaddrv6": "fd00::50",
                    "hostname": "server01",
                    "descr": "Main Server IPv6",
                }
            ]
        }
        return mock

    def test_migrate_dhcpv4_basic(self, manager: ISCToKeaMigrationManager, mock_isc_service):
        """Test basic DHCPv4 migration."""
        with patch(
            "infrafoundry.providers.opnsense.components.isc_to_kea_migration.ISCDHCPService.from_environment",
            return_value=mock_isc_service,
        ):
            result = manager.migrate_dhcpv4("dev", "opnsense")

            # Should have 1 subnet and 1 reservation
            assert len(result["subnets"]) == 1
            assert len(result["reservations"]) == 1

            # Check subnet conversion
            subnet = result["subnets"][0]
            assert subnet["name"] == "lan-dhcp"
            assert subnet["config"]["subnet"] == "192.168.1.0/24"
            assert subnet["config"]["interface"] == "lan"
            assert len(subnet["config"]["pools"]) == 1
            assert subnet["config"]["pools"][0]["range"] == "192.168.1.100 - 192.168.1.200"
            assert subnet["config"]["router"] == "192.168.1.1"
            assert subnet["config"]["domain"] == "example.local"
            assert subnet["config"]["dns_servers"] == ["192.168.1.1", "8.8.8.8"]
            assert subnet["config"]["ntp_servers"] == ["192.168.1.1"]
            assert subnet["config"]["valid_lifetime"] == 7200
            assert subnet["config"]["max_lifetime"] == 86400

            # Check reservation conversion
            reservation = result["reservations"][0]
            assert reservation["name"] == "server01"
            assert reservation["config"]["subnet"] == "192.168.1.0/24"
            assert reservation["config"]["hw_address"] == "00:11:22:33:44:55"
            assert reservation["config"]["ip_address"] == "192.168.1.50"
            assert reservation["config"]["hostname"] == "server01"
            assert reservation["config"]["description"] == "Main Server"

    def test_migrate_dhcpv4_interface_filter(
        self, manager: ISCToKeaMigrationManager, mock_isc_service
    ):
        """Test DHCPv4 migration with interface filter."""
        # Add another interface to the mock
        mock_isc_service.get_dhcpv4_config.return_value = {
            "lan": {"enable": "1", "subnet": "192.168.1.0", "subnet_bits": "24"},
            "opt1": {"enable": "1", "subnet": "192.168.2.0", "subnet_bits": "24"},
        }
        mock_isc_service.get_dhcpv4_static_maps.return_value = {"lan": [], "opt1": []}

        with patch(
            "infrafoundry.providers.opnsense.components.isc_to_kea_migration.ISCDHCPService.from_environment",
            return_value=mock_isc_service,
        ):
            result = manager.migrate_dhcpv4("dev", "opnsense", interfaces=["lan"])

            # Should only have lan subnet
            assert len(result["subnets"]) == 1
            assert result["subnets"][0]["config"]["subnet"] == "192.168.1.0/24"

    def test_migrate_dhcpv4_disabled_interface(
        self, manager: ISCToKeaMigrationManager, mock_isc_service
    ):
        """Test DHCPv4 migration skips disabled interfaces."""
        mock_isc_service.get_dhcpv4_config.return_value = {
            "lan": {"enable": "0", "subnet": "192.168.1.0", "subnet_bits": "24"}
        }
        mock_isc_service.get_dhcpv4_static_maps.return_value = {"lan": []}

        with patch(
            "infrafoundry.providers.opnsense.components.isc_to_kea_migration.ISCDHCPService.from_environment",
            return_value=mock_isc_service,
        ):
            result = manager.migrate_dhcpv4("dev", "opnsense")

            # Should have no subnets (disabled)
            assert len(result["subnets"]) == 0

    def test_migrate_dhcpv6_basic(self, manager: ISCToKeaMigrationManager, mock_isc_service):
        """Test basic DHCPv6 migration."""
        with patch(
            "infrafoundry.providers.opnsense.components.isc_to_kea_migration.ISCDHCPService.from_environment",
            return_value=mock_isc_service,
        ):
            result = manager.migrate_dhcpv6("dev", "opnsense")

            # Should have 1 subnet and 1 reservation
            assert len(result["subnets"]) == 1
            assert len(result["reservations"]) == 1

            # Check subnet conversion
            subnet = result["subnets"][0]
            assert subnet["name"] == "lan-dhcpv6"
            assert subnet["config"]["subnet"] == "fd00::/64"
            assert subnet["config"]["interface"] == "lan"
            assert len(subnet["config"]["pools"]) == 1
            assert subnet["config"]["pools"][0]["range"] == "fd00::1000 - fd00::2000"
            assert subnet["config"]["dns_servers"] == ["fd00::1"]
            assert subnet["config"]["dns_search_list"] == ["example.local"]
            assert subnet["config"]["valid_lifetime"] == 7200

            # Check reservation conversion
            reservation = result["reservations"][0]
            assert reservation["name"] == "server01"
            assert reservation["config"]["subnet"] == "fd00::/64"
            assert reservation["config"]["duid"] == "00:01:00:01:12:34:56:78:00:11:22:33:44:55"
            assert reservation["config"]["ip_address"] == "fd00::50"
            assert reservation["config"]["hostname"] == "server01"
            assert reservation["config"]["description"] == "Main Server IPv6"

    def test_migrate_all(self, manager: ISCToKeaMigrationManager, mock_isc_service):
        """Test migrating both DHCPv4 and DHCPv6."""
        with patch(
            "infrafoundry.providers.opnsense.components.isc_to_kea_migration.ISCDHCPService.from_environment",
            return_value=mock_isc_service,
        ):
            result = manager.migrate_all("dev", "opnsense")

            # Should have both v4 and v6 sections
            assert "dhcpv4" in result
            assert "dhcpv6" in result

            # Check DHCPv4
            assert len(result["dhcpv4"]["subnets"]) == 1
            assert len(result["dhcpv4"]["reservations"]) == 1

            # Check DHCPv6
            assert len(result["dhcpv6"]["subnets"]) == 1
            assert len(result["dhcpv6"]["reservations"]) == 1

    def test_export_to_yaml(self, manager: ISCToKeaMigrationManager, mock_isc_service):
        """Test exporting migration to YAML format."""
        with patch(
            "infrafoundry.providers.opnsense.components.isc_to_kea_migration.ISCDHCPService.from_environment",
            return_value=mock_isc_service,
        ):
            yaml_output = manager.export_to_yaml("dev", "opnsense")

            # Should be valid YAML string
            assert isinstance(yaml_output, str)
            assert "resources:" in yaml_output

            # Should contain all resource types
            assert "kea_subnet" in yaml_output
            assert "kea_reservation" in yaml_output
            assert "kea_dhcp6_subnet" in yaml_output
            assert "kea_dhcp6_reservation" in yaml_output

            # Should contain converted data
            assert "192.168.1.0/24" in yaml_output
            assert "fd00::/64" in yaml_output
            assert "server01" in yaml_output

    def test_convert_dhcpv4_subnet_minimal(self, manager: ISCToKeaMigrationManager):
        """Test converting minimal ISC DHCPv4 subnet."""
        isc_config = {
            "enable": "1",
            "subnet": "10.0.0.0",
            "subnet_bits": "16",
        }

        result = manager._convert_dhcpv4_subnet("opt1", isc_config)

        assert result is not None
        assert result["name"] == "opt1-dhcp"
        assert result["config"]["subnet"] == "10.0.0.0/16"
        assert result["config"]["interface"] == "opt1"
        assert result["config"]["pools"] == []

    def test_convert_dhcpv4_reservation_minimal(self, manager: ISCToKeaMigrationManager):
        """Test converting minimal ISC DHCPv4 static map."""
        static_map = {
            "mac": "aa:bb:cc:dd:ee:ff",
            "ipaddr": "10.0.0.100",
        }
        subnet_config = {
            "subnet": "10.0.0.0",
            "subnet_bits": "16",
        }

        result = manager._convert_dhcpv4_reservation("opt1", static_map, subnet_config)

        assert result is not None
        assert result["config"]["hw_address"] == "aa:bb:cc:dd:ee:ff"
        assert result["config"]["ip_address"] == "10.0.0.100"
        assert result["config"]["subnet"] == "10.0.0.0/16"

    def test_convert_dhcpv4_reservation_without_mac(self, manager: ISCToKeaMigrationManager):
        """Test that reservation without MAC is skipped."""
        static_map = {
            "ipaddr": "10.0.0.100",
        }
        subnet_config = {
            "subnet": "10.0.0.0",
            "subnet_bits": "16",
        }

        result = manager._convert_dhcpv4_reservation("opt1", static_map, subnet_config)

        assert result is None

    def test_empty_configuration(self, manager: ISCToKeaMigrationManager):
        """Test migration with empty configuration."""
        mock_service = MagicMock()
        mock_service.get_dhcpv4_config.return_value = {}
        mock_service.get_dhcpv4_static_maps.return_value = {}

        with patch(
            "infrafoundry.providers.opnsense.components.isc_to_kea_migration.ISCDHCPService.from_environment",
            return_value=mock_service,
        ):
            result = manager.migrate_dhcpv4("dev", "opnsense")

            assert len(result["subnets"]) == 0
            assert len(result["reservations"]) == 0
