"""Unit tests for ProxmoxConfigExporter."""

from unittest.mock import Mock, patch

import pytest
import requests
import yaml

from infrafoundry.providers.proxmox.exporter import ProxmoxConfigExporter


@pytest.mark.unit
class TestProxmoxConfigExporter:
    """Tests for ProxmoxConfigExporter."""

    @pytest.fixture
    def env_config(self):
        """Create a sample environment config."""
        return {
            "provider_settings": {
                "proxmox": {
                    "api_url": "https://proxmox.example.com:8006/api2/json",
                    "api_token_id": "user@pam!token",
                    "api_token_secret": "secret-value",
                    "verify_ssl": True,
                    "node": "pve1",
                }
            }
        }

    @pytest.fixture
    def env_config_no_ssl(self):
        """Create a sample environment config with SSL verification disabled."""
        return {
            "provider_settings": {
                "proxmox": {
                    "api_url": "https://proxmox.example.com:8006/api2/json",
                    "api_token_id": "user@pam!token",
                    "api_token_secret": "secret-value",
                    "verify_ssl": False,
                }
            }
        }

    @pytest.fixture
    def exporter(self, env_config):
        """Create ProxmoxConfigExporter instance."""
        return ProxmoxConfigExporter(env_config)

    def test_init(self, exporter):
        """Test ProxmoxConfigExporter initialization."""
        assert exporter.api_url == "https://proxmox.example.com:8006/api2/json"
        assert exporter.api_token_id == "user@pam!token"
        assert exporter.api_token_secret == "secret-value"
        assert exporter.verify_ssl is True
        assert exporter.node == "pve1"

    def test_init_defaults_verify_ssl_to_true(self):
        """Test that verify_ssl defaults to True for security."""
        config = {
            "provider_settings": {
                "proxmox": {
                    "api_url": "https://proxmox.example.com:8006/api2/json",
                    "api_token_id": "user@pam!token",
                    "api_token_secret": "secret-value",
                }
            }
        }
        exporter = ProxmoxConfigExporter(config)
        assert exporter.verify_ssl is True

    def test_init_respects_verify_ssl_false(self, env_config_no_ssl):
        """Test that verify_ssl can be explicitly set to False."""
        exporter = ProxmoxConfigExporter(env_config_no_ssl)
        assert exporter.verify_ssl is False

    def test_build_token_from_separate_fields(self, exporter):
        """Test token building from api_token_id and api_token_secret."""
        token = exporter._build_token()
        assert token == "user@pam!token=secret-value"

    def test_build_token_from_api_token(self):
        """Test token building from api_token directly."""
        config = {
            "provider_settings": {
                "proxmox": {
                    "api_url": "https://proxmox.example.com:8006/api2/json",
                    "api_token": "user@pam!token=secret-value",
                }
            }
        }
        exporter = ProxmoxConfigExporter(config)
        token = exporter._build_token()
        assert token == "user@pam!token=secret-value"

    def test_build_token_raises_when_no_credentials(self):
        """Test that _build_token raises ValueError when no credentials provided."""
        config = {
            "provider_settings": {
                "proxmox": {
                    "api_url": "https://proxmox.example.com:8006/api2/json",
                }
            }
        }
        exporter = ProxmoxConfigExporter(config)
        with pytest.raises(ValueError, match="Proxmox API token not configured"):
            exporter._build_token()

    def test_session_property_creates_session(self, exporter):
        """Test that session property creates and configures a session."""
        session = exporter.session
        assert session is not None
        assert isinstance(session, requests.Session)
        assert "Authorization" in session.headers
        assert session.verify is True

    def test_session_property_reuses_session(self, exporter):
        """Test that session property reuses the same session."""
        session1 = exporter.session
        session2 = exporter.session
        assert session1 is session2

    def test_close_closes_session(self, exporter):
        """Test that close() closes the session."""
        _ = exporter.session  # Create session first
        exporter.close()
        assert exporter._session is None

    def test_fetch_success(self, exporter):
        """Test successful API fetch."""
        mock_response = Mock()
        mock_response.json.return_value = {"data": [{"id": 1, "name": "test"}]}
        mock_response.raise_for_status = Mock()

        mock_session = Mock()
        mock_session.get.return_value = mock_response
        exporter._session = mock_session

        result = exporter._fetch("/test")

        assert result == [{"id": 1, "name": "test"}]
        mock_session.get.assert_called_once_with(
            "https://proxmox.example.com:8006/api2/json/test",
            timeout=30,
        )

    def test_fetch_handles_non_list_data(self, exporter):
        """Test _fetch returns empty list when data is not a list."""
        mock_response = Mock()
        mock_response.json.return_value = {"data": {"single": "object"}}
        mock_response.raise_for_status = Mock()

        mock_session = Mock()
        mock_session.get.return_value = mock_response
        exporter._session = mock_session

        result = exporter._fetch("/test")

        assert result == []

    def test_fetch_handles_http_error(self, exporter):
        """Test _fetch raises exception on HTTP error."""
        mock_session = Mock()
        mock_session.get.side_effect = requests.exceptions.HTTPError("404 Not Found")
        exporter._session = mock_session

        with pytest.raises(requests.exceptions.HTTPError):
            exporter._fetch("/test")

    def test_fetch_handles_timeout(self, exporter):
        """Test _fetch raises exception on timeout."""
        mock_session = Mock()
        mock_session.get.side_effect = requests.exceptions.Timeout("Timeout")
        exporter._session = mock_session

        with pytest.raises(requests.exceptions.Timeout):
            exporter._fetch("/test")

    def test_fetch_nodes(self, exporter):
        """Test fetching nodes."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "data": [
                {"node": "pve1", "status": "online"},
                {"node": "pve2", "status": "online"},
            ]
        }
        mock_response.raise_for_status = Mock()

        mock_session = Mock()
        mock_session.get.return_value = mock_response
        exporter._session = mock_session

        nodes = exporter._fetch_nodes()

        assert len(nodes) == 2
        assert nodes[0]["node"] == "pve1"
        assert nodes[1]["node"] == "pve2"

    def test_export_vms(self, exporter):
        """Test exporting VMs."""
        # Mock nodes
        nodes = [{"node": "pve1"}, {"node": "pve2"}]

        # Mock VMs
        def mock_get_side_effect(url, **kwargs):
            response = Mock()
            response.raise_for_status = Mock()
            if "/pve1/qemu" in url:
                response.json.return_value = {
                    "data": [
                        {
                            "vmid": 100,
                            "name": "test-vm",
                            "cores": 2,
                            "maxmem": 2147483648,  # 2GB in bytes
                            "status": "running",
                        }
                    ]
                }
            elif "/pve2/qemu" in url:
                response.json.return_value = {"data": []}
            return response

        mock_session = Mock()
        mock_session.get.side_effect = mock_get_side_effect
        exporter._session = mock_session

        result = exporter._export_vms(nodes)

        assert "pve1-vms.yaml" in result
        assert "pve2-vms.yaml" not in result

        vm_data = yaml.safe_load(result["pve1-vms.yaml"])
        assert len(vm_data["resources"]) == 1
        assert vm_data["resources"][0]["name"] == "test-vm"
        assert vm_data["resources"][0]["type"] == "vm"
        assert vm_data["resources"][0]["provider"] == "proxmox"
        assert vm_data["resources"][0]["config"]["vmid"] == 100
        assert vm_data["resources"][0]["config"]["cores"] == 2
        # Verify memory conversion: 2147483648 bytes = 2048 MiB
        assert vm_data["resources"][0]["config"]["memory"] == 2048

    def test_export_vms_generates_name_when_missing(self, exporter):
        """Test that VM export generates name from vmid when name is missing."""
        nodes = [{"node": "pve1"}]

        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {
            "data": [
                {
                    "vmid": 100,
                    "cores": 2,
                    "maxmem": 2147483648,
                    "status": "running",
                }
            ]
        }

        mock_session = Mock()
        mock_session.get.return_value = mock_response
        exporter._session = mock_session

        result = exporter._export_vms(nodes)

        vm_data = yaml.safe_load(result["pve1-vms.yaml"])
        assert vm_data["resources"][0]["name"] == "vm-100"

    def test_export_vms_memory_conversion(self, exporter):
        """Test that VM memory is correctly converted from bytes to MiB."""
        nodes = [{"node": "pve1"}]

        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {
            "data": [
                {"vmid": 100, "name": "vm-2gb", "maxmem": 2147483648},  # 2GB = 2048 MiB
                {"vmid": 101, "name": "vm-4gb", "maxmem": 4294967296},  # 4GB = 4096 MiB
                {"vmid": 102, "name": "vm-512mb", "maxmem": 536870912},  # 512MB = 512 MiB
                {"vmid": 103, "name": "vm-none", "maxmem": None},  # Should handle None
            ]
        }

        mock_session = Mock()
        mock_session.get.return_value = mock_response
        exporter._session = mock_session

        result = exporter._export_vms(nodes)

        vm_data = yaml.safe_load(result["pve1-vms.yaml"])
        assert len(vm_data["resources"]) == 4

        # Verify conversions
        assert vm_data["resources"][0]["config"]["memory"] == 2048
        assert vm_data["resources"][1]["config"]["memory"] == 4096
        assert vm_data["resources"][2]["config"]["memory"] == 512
        assert vm_data["resources"][3]["config"]["memory"] is None

    def test_export_networks(self, exporter):
        """Test exporting networks."""
        nodes = [{"node": "pve1"}]

        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {
            "data": [
                {"iface": "vmbr0", "type": "bridge", "cidr": "10.0.0.1/24"},
                {"iface": "eth0", "type": "eth", "cidr": ""},  # Should be filtered out
            ]
        }

        mock_session = Mock()
        mock_session.get.return_value = mock_response
        exporter._session = mock_session

        result = exporter._export_networks(nodes)

        assert "pve1-networks.yaml" in result
        network_data = yaml.safe_load(result["pve1-networks.yaml"])
        assert len(network_data["resources"]) == 1
        assert network_data["resources"][0]["name"] == "vmbr0"
        assert network_data["resources"][0]["type"] == "network"
        assert network_data["resources"][0]["config"]["bridge"] == "vmbr0"

    def test_export_storage(self, exporter):
        """Test exporting storage."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {
            "data": [
                {
                    "storage": "local",
                    "type": "dir",
                    "content": "images,rootdir",
                    "nodes": "pve1,pve2",
                }
            ]
        }

        mock_session = Mock()
        mock_session.get.return_value = mock_response
        exporter._session = mock_session

        result = exporter._export_storage([])

        assert "storage.yaml" in result
        storage_data = yaml.safe_load(result["storage.yaml"])
        assert len(storage_data["resources"]) == 1
        assert storage_data["resources"][0]["name"] == "local"
        assert storage_data["resources"][0]["type"] == "storage"
        assert storage_data["resources"][0]["config"]["type"] == "dir"

    @patch.object(ProxmoxConfigExporter, "_fetch_nodes")
    @patch.object(ProxmoxConfigExporter, "_export_vms")
    @patch.object(ProxmoxConfigExporter, "_export_networks")
    @patch.object(ProxmoxConfigExporter, "_export_storage")
    @patch.object(ProxmoxConfigExporter, "close")
    def test_export_all_resources(
        self, mock_close, mock_storage, mock_networks, mock_vms, mock_nodes, exporter
    ):
        """Test export without filters exports all resource types."""
        mock_nodes.return_value = [{"node": "pve1"}]
        mock_vms.return_value = {"pve1-vms.yaml": "vm: content"}
        mock_networks.return_value = {"pve1-networks.yaml": "network: content"}
        mock_storage.return_value = {"storage.yaml": "storage: content"}

        result = exporter.export()

        assert len(result) == 3
        assert "pve1-vms.yaml" in result
        assert "pve1-networks.yaml" in result
        assert "storage.yaml" in result
        mock_vms.assert_called_once()
        mock_networks.assert_called_once()
        mock_storage.assert_called_once()
        mock_close.assert_called_once()

    @patch.object(ProxmoxConfigExporter, "_fetch_nodes")
    @patch.object(ProxmoxConfigExporter, "_export_vms")
    @patch.object(ProxmoxConfigExporter, "_export_networks")
    @patch.object(ProxmoxConfigExporter, "_export_storage")
    @patch.object(ProxmoxConfigExporter, "close")
    def test_export_with_node_filter(
        self, mock_close, mock_storage, mock_networks, mock_vms, mock_nodes, exporter
    ):
        """Test export with node filter."""
        mock_nodes.return_value = [{"node": "pve1"}, {"node": "pve2"}]
        mock_vms.return_value = {}
        mock_networks.return_value = {}
        mock_storage.return_value = {}

        exporter.export(node_filter="pve2")

        # Should only pass filtered nodes
        call_args = mock_vms.call_args[0][0]
        assert len(call_args) == 1
        assert call_args[0]["node"] == "pve2"

    @patch.object(ProxmoxConfigExporter, "_fetch_nodes")
    @patch.object(ProxmoxConfigExporter, "_export_vms")
    @patch.object(ProxmoxConfigExporter, "_export_networks")
    @patch.object(ProxmoxConfigExporter, "_export_storage")
    @patch.object(ProxmoxConfigExporter, "close")
    def test_export_with_vm_filter(
        self, mock_close, mock_storage, mock_networks, mock_vms, mock_nodes, exporter
    ):
        """Test export with resource_filter='vm' only exports VMs."""
        mock_nodes.return_value = [{"node": "pve1"}]
        mock_vms.return_value = {"pve1-vms.yaml": "content"}

        exporter.export(resource_filter="vm")

        mock_vms.assert_called_once()
        mock_networks.assert_not_called()
        mock_storage.assert_not_called()

    @patch.object(ProxmoxConfigExporter, "_fetch_nodes")
    @patch.object(ProxmoxConfigExporter, "_export_vms")
    @patch.object(ProxmoxConfigExporter, "_export_networks")
    @patch.object(ProxmoxConfigExporter, "_export_storage")
    @patch.object(ProxmoxConfigExporter, "close")
    def test_export_with_network_filter(
        self, mock_close, mock_storage, mock_networks, mock_vms, mock_nodes, exporter
    ):
        """Test export with resource_filter='network' only exports networks."""
        mock_nodes.return_value = [{"node": "pve1"}]
        mock_networks.return_value = {"pve1-networks.yaml": "content"}

        exporter.export(resource_filter="network")

        mock_vms.assert_not_called()
        mock_networks.assert_called_once()
        mock_storage.assert_not_called()

    @patch.object(ProxmoxConfigExporter, "_fetch_nodes")
    @patch.object(ProxmoxConfigExporter, "_export_vms")
    @patch.object(ProxmoxConfigExporter, "_export_networks")
    @patch.object(ProxmoxConfigExporter, "_export_storage")
    @patch.object(ProxmoxConfigExporter, "close")
    def test_export_with_storage_filter(
        self, mock_close, mock_storage, mock_networks, mock_vms, mock_nodes, exporter
    ):
        """Test export with resource_filter='storage' only exports storage."""
        mock_nodes.return_value = [{"node": "pve1"}]
        mock_storage.return_value = {"storage.yaml": "content"}

        exporter.export(resource_filter="storage")

        mock_vms.assert_not_called()
        mock_networks.assert_not_called()
        mock_storage.assert_called_once()

    def test_export_raises_when_no_api_url(self):
        """Test export raises ValueError when api_url not configured."""
        config = {"provider_settings": {"proxmox": {}}}
        exporter = ProxmoxConfigExporter(config)

        with pytest.raises(ValueError, match="Proxmox api_url not configured"):
            exporter.export()

    def test_session_respects_verify_ssl_setting(self, env_config_no_ssl):
        """Test that session respects the verify_ssl setting."""
        exporter = ProxmoxConfigExporter(env_config_no_ssl)
        session = exporter.session
        assert session.verify is False
