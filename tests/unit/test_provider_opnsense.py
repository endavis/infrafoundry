"""Unit tests for OPNsense provider reset and migrate functionality."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.providers.opnsense import OPNsenseProvider


class TestOPNsenseProviderReset:
    """Tests for OPNsense provider reset methods."""

    @pytest.fixture
    def provider(self):
        """Create OPNsense provider instance for testing."""
        return OPNsenseProvider(config_dir=Path("."), output_dir=Path("."))

    @pytest.fixture
    def mock_config_manager(self):
        """Mock ConfigManager for environment loading."""
        with patch("infrafoundry.core.config.ConfigManager") as mock:
            mock_instance = MagicMock()
            mock.return_value = mock_instance

            # Mock environment config
            mock_env = MagicMock()
            mock_env.get_provider_settings.return_value = {
                "api_key": "test_key",
                "api_secret": "test_secret",
                "api_url": "https://test.example.com",
                "verify_ssl": False,
            }
            mock_instance.load_environment.return_value = mock_env

            yield mock

    @pytest.fixture
    def mock_client(self):
        """Mock OPNsenseClient for API calls."""
        with patch("infrafoundry.providers.opnsense.api_client.OPNsenseClient") as mock:
            mock_instance = MagicMock()
            mock.return_value = mock_instance
            yield mock_instance

    @pytest.fixture
    def mock_kea_client(self):
        """Mock KeaClient for DHCPv6 operations."""
        with patch("infrafoundry.providers.opnsense.api_client.KeaClient") as mock:
            mock_instance = MagicMock()
            mock.return_value = mock_instance
            yield mock_instance

    def test_reset_kea_dhcpv4_deletes_all_reservations_and_subnets(
        self, provider, mock_config_manager, mock_client
    ):
        """Test reset_kea_dhcpv4 deletes all reservations and subnets."""
        # Setup mock responses
        mock_client.request.side_effect = [
            # Search reservations
            {
                "rows": [
                    {"uuid": "res-1", "hostname": "host1"},
                    {"uuid": "res-2", "hostname": "host2"},
                ]
            },
            # Delete reservation 1
            {"result": "deleted"},
            # Delete reservation 2
            {"result": "deleted"},
            # Search subnets
            {
                "rows": [
                    {"uuid": "subnet-1", "description": "Subnet 1"},
                    {"uuid": "subnet-2", "description": "Subnet 2"},
                ]
            },
            # Delete subnet 1
            {"result": "deleted"},
            # Delete subnet 2
            {"result": "deleted"},
            # Reconfigure service
            {"result": "ok"},
        ]

        # Execute reset
        provider.reset_kea_dhcpv4("test_env")

        # Verify API calls
        assert mock_client.request.call_count == 7
        mock_client.request.assert_any_call("GET", "kea/dhcpv4/searchReservation")
        mock_client.request.assert_any_call("POST", "kea/dhcpv4/delReservation/res-1")
        mock_client.request.assert_any_call("POST", "kea/dhcpv4/delReservation/res-2")
        mock_client.request.assert_any_call("GET", "kea/dhcpv4/searchSubnet")
        mock_client.request.assert_any_call("POST", "kea/dhcpv4/delSubnet/subnet-1")
        mock_client.request.assert_any_call("POST", "kea/dhcpv4/delSubnet/subnet-2")
        mock_client.request.assert_any_call("POST", "kea/service/reconfigure")

    def test_reset_kea_dhcpv4_handles_empty_config(
        self, provider, mock_config_manager, mock_client
    ):
        """Test reset_kea_dhcpv4 handles empty configuration gracefully."""
        # Setup mock responses - no reservations or subnets
        mock_client.request.side_effect = [
            {"rows": []},  # Search reservations - empty
            {"rows": []},  # Search subnets - empty
            {"result": "ok"},  # Reconfigure
        ]

        # Execute reset
        provider.reset_kea_dhcpv4("test_env")

        # Verify only search and reconfigure were called
        assert mock_client.request.call_count == 3

    def test_reset_kea_dhcpv4_raises_on_missing_provider_settings(
        self, provider, mock_config_manager
    ):
        """Test reset_kea_dhcpv4 raises error when provider settings are missing."""
        # Setup mock to return None for provider settings
        mock_env = MagicMock()
        mock_env.get_provider_settings.return_value = None
        mock_config_manager.return_value.load_environment.return_value = mock_env

        # Execute and expect error
        with pytest.raises(ValueError, match="No OPNsense provider settings"):
            provider.reset_kea_dhcpv4("test_env")

    def test_reset_kea_dhcpv6_deletes_all_reservations_and_subnets(
        self, provider, mock_config_manager, mock_client, mock_kea_client
    ):
        """Test reset_kea_dhcpv6 deletes all reservations and subnets."""
        # Setup mock responses
        mock_kea_client.search_dhcp6_reservations.return_value = [
            {"uuid": "res-v6-1", "hostname": "host1"},
            {"uuid": "res-v6-2", "hostname": "host2"},
        ]
        mock_kea_client.search_dhcp6_subnets.return_value = [
            {"uuid": "subnet-v6-1", "description": "IPv6 Subnet 1"},
            {"uuid": "subnet-v6-2", "description": "IPv6 Subnet 2"},
        ]

        # Execute reset
        provider.reset_kea_dhcpv6("test_env")

        # Verify DHCPv6 operations
        mock_kea_client.search_dhcp6_reservations.assert_called_once()
        mock_kea_client.delete_dhcp6_reservation.assert_any_call("res-v6-1")
        mock_kea_client.delete_dhcp6_reservation.assert_any_call("res-v6-2")
        mock_kea_client.search_dhcp6_subnets.assert_called_once()
        mock_kea_client.delete_dhcp6_subnet.assert_any_call("subnet-v6-1")
        mock_kea_client.delete_dhcp6_subnet.assert_any_call("subnet-v6-2")
        mock_kea_client.reconfigure_service.assert_called_once()

    def test_reset_kea_dhcpv6_handles_empty_config(
        self, provider, mock_config_manager, mock_client, mock_kea_client
    ):
        """Test reset_kea_dhcpv6 handles empty configuration gracefully."""
        # Setup mock responses - no reservations or subnets
        mock_kea_client.search_dhcp6_reservations.return_value = []
        mock_kea_client.search_dhcp6_subnets.return_value = []

        # Execute reset
        provider.reset_kea_dhcpv6("test_env")

        # Verify no delete operations, only search and reconfigure
        mock_kea_client.delete_dhcp6_reservation.assert_not_called()
        mock_kea_client.delete_dhcp6_subnet.assert_not_called()
        mock_kea_client.reconfigure_service.assert_called_once()


class TestOPNsenseProviderMigrate:
    """Tests for OPNsense provider migrate functionality."""

    @pytest.fixture
    def provider(self):
        """Create OPNsense provider instance for testing."""
        return OPNsenseProvider(config_dir=Path("."), output_dir=Path("."))

    @pytest.fixture
    def mock_config_manager(self):
        """Mock ConfigManager for environment loading."""
        with patch("infrafoundry.core.config.ConfigManager") as mock:
            mock_instance = MagicMock()
            mock.return_value = mock_instance

            # Mock environment config
            mock_env = MagicMock()
            mock_env.get_provider_settings.return_value = {
                "api_key": "test_key",
                "api_secret": "test_secret",
                "api_url": "https://test.example.com",
                "verify_ssl": False,
            }
            mock_instance.load_environment.return_value = mock_env

            yield mock

    @pytest.fixture
    def mock_client(self):
        """Mock OPNsenseClient for API calls."""
        with patch("infrafoundry.providers.opnsense.api_client.OPNsenseClient") as mock:
            mock_instance = MagicMock()
            mock.return_value = mock_instance
            yield mock_instance

    @pytest.fixture
    def mock_kea_client(self):
        """Mock KeaClient for DHCPv6 operations."""
        with patch("infrafoundry.providers.opnsense.api_client.KeaClient") as mock:
            mock_instance = MagicMock()
            mock.return_value = mock_instance
            yield mock_instance

    def test_migrate_kea_dhcp_generates_yaml_for_dhcpv4_subnets(
        self, provider, mock_config_manager, mock_client, mock_kea_client
    ):
        """Test migrate_kea_dhcp generates YAML for DHCPv4 subnets."""
        # Setup mock responses
        mock_client.request.side_effect = [
            # Search DHCPv4 subnets
            {
                "rows": [
                    {
                        "uuid": "subnet-1",
                        "subnet": "192.168.1.0/24",
                        "description": "LAN Network",
                        "pools": "192.168.1.10 - 192.168.1.20",
                        "option_data_autocollect": "1",
                        "option_data_dns_servers": "8.8.8.8,8.8.4.4",
                        "option_data_routers": "192.168.1.1",
                    }
                ]
            },
            # Search DHCPv4 reservations
            {"rows": []},
        ]
        mock_kea_client.search_dhcp6_subnets.return_value = []
        mock_kea_client.search_dhcp6_reservations.return_value = []

        # Execute migration
        yaml_output = provider.migrate_kea_dhcp("test_env")

        # Verify YAML output contains expected data
        assert "provider: opnsense" in yaml_output
        assert "type: kea_subnet" in yaml_output
        assert "name: lan_network" in yaml_output
        assert "subnet: 192.168.1.0/24" in yaml_output
        assert "192.168.1.10 - 192.168.1.20" in yaml_output
        assert "description: LAN Network" in yaml_output
        assert "auto_collect: true" in yaml_output
        assert "8.8.8.8" in yaml_output

    def test_migrate_kea_dhcp_generates_yaml_for_dhcpv4_reservations(
        self, provider, mock_config_manager, mock_client, mock_kea_client
    ):
        """Test migrate_kea_dhcp generates YAML for DHCPv4 reservations."""
        # Setup mock responses
        mock_client.request.side_effect = [
            # Search DHCPv4 subnets
            {"rows": []},
            # Search DHCPv4 reservations
            {
                "rows": [
                    {
                        "uuid": "res-1",
                        "subnet": "subnet-uuid-1",
                        "hw_address": "aa:bb:cc:dd:ee:ff",
                        "ip_address": "192.168.1.50",
                        "hostname": "web-server",
                        "description": "Production web server",
                    }
                ]
            },
        ]
        mock_kea_client.search_dhcp6_subnets.return_value = []
        mock_kea_client.search_dhcp6_reservations.return_value = []

        # Execute migration
        yaml_output = provider.migrate_kea_dhcp("test_env")

        # Verify YAML output contains expected data
        assert "type: kea_reservation" in yaml_output
        assert "name: web_server" in yaml_output
        assert "hw_address: aa:bb:cc:dd:ee:ff" in yaml_output
        assert "ip_address: 192.168.1.50" in yaml_output
        assert "hostname: web-server" in yaml_output

    def test_migrate_kea_dhcp_generates_yaml_for_dhcpv6_subnets(
        self, provider, mock_config_manager, mock_client, mock_kea_client
    ):
        """Test migrate_kea_dhcp generates YAML for DHCPv6 subnets."""
        # Setup mock responses
        mock_client.request.side_effect = [
            {"rows": []},  # DHCPv4 subnets
            {"rows": []},  # DHCPv4 reservations
        ]
        mock_kea_client.search_dhcp6_subnets.return_value = [
            {
                "uuid": "subnet-v6-1",
                "subnet": "fd00::/64",
                "description": "IPv6 LAN",
                "option_data_autocollect": "1",
                "option_data_dns_servers": "2001:4860:4860::8888",
            }
        ]
        mock_kea_client.search_dhcp6_reservations.return_value = []

        # Execute migration
        yaml_output = provider.migrate_kea_dhcp("test_env")

        # Verify YAML output contains expected data
        assert "type: kea_dhcp6_subnet" in yaml_output
        assert "name: ipv6_lan_v6" in yaml_output
        assert "subnet: fd00::/64" in yaml_output
        assert "description: IPv6 LAN" in yaml_output

    def test_migrate_kea_dhcp_generates_yaml_for_dhcpv6_reservations(
        self, provider, mock_config_manager, mock_client, mock_kea_client
    ):
        """Test migrate_kea_dhcp generates YAML for DHCPv6 reservations."""
        # Setup mock responses
        mock_client.request.side_effect = [
            {"rows": []},  # DHCPv4 subnets
            {"rows": []},  # DHCPv4 reservations
        ]
        mock_kea_client.search_dhcp6_subnets.return_value = []
        mock_kea_client.search_dhcp6_reservations.return_value = [
            {
                "uuid": "res-v6-1",
                "subnet": "subnet-v6-uuid-1",
                "duid": "00:01:00:01:2c:3d:4e:5f:6a:7b:8c:9d",
                "ip_address": "fd00::50",
                "hostname": "server-ipv6",
                "description": "IPv6 server reservation",
            }
        ]

        # Execute migration
        yaml_output = provider.migrate_kea_dhcp("test_env")

        # Verify YAML output contains expected data
        assert "type: kea_dhcp6_reservation" in yaml_output
        assert "name: server_ipv6_v6" in yaml_output
        assert "duid: 00:01:00:01:2c:3d:4e:5f:6a:7b:8c:9d" in yaml_output
        assert "ip_address: fd00::50" in yaml_output

    def test_migrate_kea_dhcp_handles_empty_configuration(
        self, provider, mock_config_manager, mock_client, mock_kea_client
    ):
        """Test migrate_kea_dhcp handles empty configuration gracefully."""
        # Setup mock responses - all empty
        mock_client.request.side_effect = [
            {"rows": []},  # DHCPv4 subnets
            {"rows": []},  # DHCPv4 reservations
        ]
        mock_kea_client.search_dhcp6_subnets.return_value = []
        mock_kea_client.search_dhcp6_reservations.return_value = []

        # Execute migration
        yaml_output = provider.migrate_kea_dhcp("test_env")

        # Verify minimal YAML structure
        assert "resources:" in yaml_output
        # Should be almost empty (just "resources: []\n" or similar)
        assert len(yaml_output) < 50

    def test_migrate_kea_dhcp_sanitizes_resource_names(
        self, provider, mock_config_manager, mock_client, mock_kea_client
    ):
        """Test migrate_kea_dhcp properly sanitizes resource names."""
        # Setup mock with complex names
        mock_client.request.side_effect = [
            {
                "rows": [
                    {
                        "uuid": "subnet-1",
                        "subnet": "192.168.1.0/24",
                        "description": "OPT1 - Infrastructure VLAN (Proxmox, Ansible)",
                        "pools": "192.168.1.10 - 192.168.1.20",
                    }
                ]
            },
            {
                "rows": [
                    {
                        "uuid": "res-1",
                        "subnet": "subnet-uuid-1",
                        "hw_address": "aa:bb:cc:dd:ee:ff",
                        "ip_address": "192.168.1.50",
                        "hostname": "Web-Server-01",
                    }
                ]
            },
        ]
        mock_kea_client.search_dhcp6_subnets.return_value = []
        mock_kea_client.search_dhcp6_reservations.return_value = []

        # Execute migration
        yaml_output = provider.migrate_kea_dhcp("test_env")

        # Verify name sanitization (spaces and special chars replaced)
        assert "name: opt1_-_infrastructure_vlan_(proxmox,_ansible)" in yaml_output
        assert "name: web_server_01" in yaml_output

    def test_migrate_kea_dhcp_raises_on_missing_provider_settings(
        self, provider, mock_config_manager
    ):
        """Test migrate_kea_dhcp raises error when provider settings are missing."""
        # Setup mock to return None for provider settings
        mock_env = MagicMock()
        mock_env.get_provider_settings.return_value = None
        mock_config_manager.return_value.load_environment.return_value = mock_env

        # Execute and expect error
        with pytest.raises(ValueError, match="No OPNsense provider settings"):
            provider.migrate_kea_dhcp("test_env")
