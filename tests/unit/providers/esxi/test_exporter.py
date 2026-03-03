"""Unit tests for ESXi EsxiConfigExporter."""

from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.providers.esxi.exporter import EsxiConfigExporter


@pytest.fixture
def env_config():
    """Create a test environment config."""
    return {
        "provider_settings": {
            "esxi": {
                "hosts": {
                    "esxi-01": {
                        "hostname": "192.168.1.10",
                        "username": "root",
                    },
                },
                "timeout": 10,
            }
        }
    }


@pytest.fixture
def exporter(env_config):
    """Create an EsxiConfigExporter instance."""
    return EsxiConfigExporter(env_config)


class TestExporterInit:
    """Tests for EsxiConfigExporter initialization."""

    def test_init_with_config(self, exporter):
        """Should extract hosts config."""
        assert "esxi-01" in exporter.hosts_config
        assert exporter.timeout == 10

    def test_init_no_hosts(self):
        """Should handle missing hosts."""
        exporter = EsxiConfigExporter({"provider_settings": {"esxi": {}}})
        assert exporter.hosts_config == {}

    def test_init_no_esxi_settings(self):
        """Should handle missing esxi settings."""
        exporter = EsxiConfigExporter({"provider_settings": {}})
        assert exporter.hosts_config == {}


class TestExport:
    """Tests for EsxiConfigExporter.export."""

    def test_export_no_hosts_raises(self):
        """Should raise ValueError when no hosts configured."""
        exporter = EsxiConfigExporter({"provider_settings": {"esxi": {}}})
        with pytest.raises(ValueError, match="No ESXi hosts configured"):
            exporter.export()

    @patch.object(EsxiConfigExporter, "_ssh_command")
    def test_export_all_resources(self, mock_ssh, exporter):
        """Should export vswitches, portgroups, and VMs."""
        mock_ssh.side_effect = [
            # vswitches
            "Name: vSwitch0\nMTU: 1500\nUplinks: vmnic0\n",
            # portgroups
            "Name VSwitch\nVM_Network vSwitch0\n",
            # vms
            "Vmid Name\n1 test-vm\n",
        ]
        exports = exporter.export()
        assert len(exports) == 3
        assert any("vswitches" in k for k in exports)
        assert any("portgroups" in k for k in exports)
        assert any("vms" in k for k in exports)

    @patch.object(EsxiConfigExporter, "_ssh_command")
    def test_export_with_host_filter(self, mock_ssh, env_config):
        """Should filter to specific host."""
        env_config["provider_settings"]["esxi"]["hosts"]["esxi-02"] = {"hostname": "192.168.1.11"}
        exporter = EsxiConfigExporter(env_config)
        mock_ssh.return_value = ""
        exporter.export(host_filter="esxi-01")
        # Should only call SSH for esxi-01, not esxi-02
        for call in mock_ssh.call_args_list:
            assert call[0][0] == "192.168.1.10"  # esxi-01's hostname

    @patch.object(EsxiConfigExporter, "_ssh_command")
    def test_export_with_resource_filter(self, mock_ssh, exporter):
        """Should export only the filtered resource type."""
        mock_ssh.return_value = "Name: vSwitch0\nMTU: 1500\nUplinks: vmnic0\n"
        exporter.export(resource_filter="vswitch")
        # Should only call ssh_command once (for vswitches)
        assert mock_ssh.call_count == 1


class TestParseVswitchList:
    """Tests for _parse_vswitch_list."""

    def test_parse_single_vswitch(self):
        """Should parse a single vswitch."""
        output = "Name: vSwitch0\nMTU: 1500\nUplinks: vmnic0\n"
        result = EsxiConfigExporter._parse_vswitch_list(output, "esxi-01")
        assert len(result) == 1
        assert result[0]["name"] == "vSwitch0"
        assert result[0]["config"]["host"] == "esxi-01"
        assert result[0]["config"]["mtu"] == 1500
        assert result[0]["config"]["uplink"] == ["vmnic0"]

    def test_parse_multiple_vswitches(self):
        """Should parse multiple vswitches."""
        output = (
            "Name: vSwitch0\nMTU: 1500\nUplinks: vmnic0\n\n"
            "Name: vSwitch1\nMTU: 9000\nUplinks: vmnic1, vmnic2\n"
        )
        result = EsxiConfigExporter._parse_vswitch_list(output, "esxi-01")
        assert len(result) == 2
        assert result[0]["name"] == "vSwitch0"
        assert result[1]["name"] == "vSwitch1"
        assert result[1]["config"]["mtu"] == 9000
        assert result[1]["config"]["uplink"] == ["vmnic1", "vmnic2"]

    def test_parse_empty_output(self):
        """Should return empty list for empty output."""
        result = EsxiConfigExporter._parse_vswitch_list("", "esxi-01")
        assert result == []

    def test_parse_vswitch_no_uplinks(self):
        """Should handle vswitch with no uplinks."""
        output = "Name: vSwitch1\nMTU: 1500\nUplinks: \n"
        result = EsxiConfigExporter._parse_vswitch_list(output, "esxi-01")
        assert len(result) == 1
        assert result[0]["config"]["uplink"] == []


class TestParsePortgroupList:
    """Tests for _parse_portgroup_list."""

    def test_parse_portgroups(self):
        """Should parse portgroup list output."""
        output = "Name VSwitch\nVM_Network vSwitch0\nmgmt_pg vSwitch1\n"
        result = EsxiConfigExporter._parse_portgroup_list(output, "esxi-01")
        assert len(result) == 2
        assert result[0]["name"] == "VM_Network"
        assert result[0]["config"]["vswitch"] == "vSwitch0"
        assert result[1]["name"] == "mgmt_pg"
        assert result[1]["config"]["vswitch"] == "vSwitch1"

    def test_parse_empty_output(self):
        """Should return empty list for empty output."""
        result = EsxiConfigExporter._parse_portgroup_list("", "esxi-01")
        assert result == []


class TestParseVMList:
    """Tests for _parse_vm_list."""

    def test_parse_vms(self):
        """Should parse VM list output."""
        output = "Vmid  Name         File\n1     test-vm     [ds1] test-vm/test-vm.vmx\n"
        result = EsxiConfigExporter._parse_vm_list(output, "esxi-01")
        assert len(result) == 1
        assert result[0]["name"] == "test-vm"
        assert result[0]["config"]["host"] == "esxi-01"

    def test_parse_empty_output(self):
        """Should return empty list for empty output."""
        result = EsxiConfigExporter._parse_vm_list("", "esxi-01")
        assert result == []

    def test_parse_multiple_vms(self):
        """Should parse multiple VMs."""
        output = "Vmid  Name\n1     vm1\n2     vm2\n3     vm3\n"
        result = EsxiConfigExporter._parse_vm_list(output, "esxi-01")
        assert len(result) == 3
        assert result[0]["name"] == "vm1"
        assert result[2]["name"] == "vm3"


class TestSSHCommand:
    """Tests for _ssh_command."""

    @patch("subprocess.run")
    def test_ssh_command_success(self, mock_run, exporter):
        """Should execute SSH command and return stdout."""
        mock_run.return_value = MagicMock(stdout="output data")
        result = exporter._ssh_command("192.168.1.10", "root", "esxcli test")
        assert result == "output data"

    @patch("subprocess.run")
    def test_ssh_command_uses_correct_args(self, mock_run, exporter):
        """Should build SSH command with correct arguments."""
        mock_run.return_value = MagicMock(stdout="")
        exporter._ssh_command("192.168.1.10", "root", "esxcli test")

        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "ssh"
        assert "root@192.168.1.10" in call_args
        assert "esxcli test" in call_args
        assert "-o" in call_args

    @patch("subprocess.run")
    def test_ssh_command_includes_timeout(self, mock_run, exporter):
        """Should include connect timeout in SSH args."""
        mock_run.return_value = MagicMock(stdout="")
        exporter._ssh_command("192.168.1.10", "root", "test")

        call_args = mock_run.call_args[0][0]
        assert "ConnectTimeout=10" in " ".join(call_args)
