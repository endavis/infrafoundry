"""Unit tests for ESXi Terraform template rendering."""

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.esxi import EsxiProvider


@pytest.fixture
def provider(tmp_path):
    """Create an EsxiProvider for template testing."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    p = EsxiProvider(config_dir, output_dir)
    p.set_environment("test")
    return p


def _make_vswitch(name: str = "vSwitch1", **config_overrides) -> ResourceConfig:
    """Helper to create a vswitch ResourceConfig."""
    config: dict = {"host": "esxi-01", **config_overrides}
    return ResourceConfig(name=name, type="vswitch", provider="esxi", config=config)


def _make_portgroup(name: str = "pg-mgmt", **config_overrides) -> ResourceConfig:
    """Helper to create a portgroup ResourceConfig."""
    config: dict = {"host": "esxi-01", "vswitch": "vSwitch1", **config_overrides}
    return ResourceConfig(name=name, type="portgroup", provider="esxi", config=config)


def _make_vm(name: str = "test-vm", **config_overrides) -> ResourceConfig:
    """Helper to create a VM ResourceConfig."""
    config: dict = {"host": "esxi-01", "name": name, **config_overrides}
    return ResourceConfig(name=name, type="vm", provider="esxi", config=config)


class TestProviderTemplate:
    """Tests for provider.tf.j2 template."""

    def test_provider_renders_hosts(self, provider):
        """Provider template should render aliased blocks for each host."""
        hosts = [
            {"name": "esxi-01", "alias": "esxi_01"},
            {"name": "esxi-02", "alias": "esxi_02"},
        ]
        content = provider.render_template("esxi/provider.tf.j2", {"hosts": hosts})
        assert 'source  = "josenk/esxi"' in content
        assert 'alias     = "esxi_01"' in content
        assert 'alias     = "esxi_02"' in content
        assert "var.esxi_hostname_esxi_01" in content
        assert "var.esxi_password_esxi_02" in content

    def test_provider_single_host(self, provider):
        """Provider template should work with a single host."""
        hosts = [{"name": "esxi-01", "alias": "esxi_01"}]
        content = provider.render_template("esxi/provider.tf.j2", {"hosts": hosts})
        assert content.count('provider "esxi"') == 1


class TestVariablesTemplate:
    """Tests for variables.tf.j2 template."""

    def test_variables_per_host(self, provider):
        """Variables should be generated for each host."""
        hosts = [
            {"name": "esxi-01", "alias": "esxi_01"},
            {"name": "esxi-02", "alias": "esxi_02"},
        ]
        content = provider.render_template("esxi/variables.tf.j2", {"hosts": hosts})
        assert '"esxi_hostname_esxi_01"' in content
        assert '"esxi_username_esxi_01"' in content
        assert '"esxi_password_esxi_01"' in content
        assert '"esxi_hostname_esxi_02"' in content
        assert "sensitive   = true" in content


class TestVswitchTemplate:
    """Tests for vswitch.tf.j2 template."""

    def test_basic_vswitch(self, provider):
        """Basic vswitch should render with provider alias."""
        vswitches = [_make_vswitch()]
        content = provider.render_template(
            "esxi/vswitch.tf.j2",
            {"vswitches": vswitches, "host_alias": EsxiProvider._host_alias},
        )
        assert 'resource "esxi_vswitch"' in content
        assert "provider = esxi.esxi_01" in content
        assert 'name     = "vSwitch1"' in content

    def test_vswitch_with_uplinks(self, provider):
        """Vswitch with uplinks should render uplink blocks."""
        vswitches = [_make_vswitch(uplink=["vmnic0", "vmnic1"])]
        content = provider.render_template(
            "esxi/vswitch.tf.j2",
            {"vswitches": vswitches, "host_alias": EsxiProvider._host_alias},
        )
        assert content.count("uplink {") == 2
        assert '"vmnic0"' in content
        assert '"vmnic1"' in content

    def test_vswitch_with_mtu(self, provider):
        """Vswitch with MTU should render mtu field."""
        vswitches = [_make_vswitch(mtu=9000)]
        content = provider.render_template(
            "esxi/vswitch.tf.j2",
            {"vswitches": vswitches, "host_alias": EsxiProvider._host_alias},
        )
        assert "mtu = 9000" in content

    def test_vswitch_with_ports(self, provider):
        """Vswitch with ports should render ports field."""
        vswitches = [_make_vswitch(ports=128)]
        content = provider.render_template(
            "esxi/vswitch.tf.j2",
            {"vswitches": vswitches, "host_alias": EsxiProvider._host_alias},
        )
        assert "ports = 128" in content


class TestPortgroupTemplate:
    """Tests for portgroup.tf.j2 template."""

    def test_basic_portgroup(self, provider):
        """Basic portgroup should render with vswitch reference."""
        portgroups = [_make_portgroup()]
        content = provider.render_template(
            "esxi/portgroup.tf.j2",
            {"portgroups": portgroups, "host_alias": EsxiProvider._host_alias},
        )
        assert 'resource "esxi_portgroup"' in content
        assert "provider = esxi.esxi_01" in content
        assert 'vswitch  = "vSwitch1"' in content

    def test_portgroup_with_vlan(self, provider):
        """Portgroup with VLAN should render vlan field."""
        portgroups = [_make_portgroup(vlan=100)]
        content = provider.render_template(
            "esxi/portgroup.tf.j2",
            {"portgroups": portgroups, "host_alias": EsxiProvider._host_alias},
        )
        assert "vlan     = 100" in content

    def test_portgroup_with_security_policies(self, provider):
        """Portgroup with security policies should render all flags."""
        portgroups = [
            _make_portgroup(
                promiscuous_mode=True,
                mac_changes=False,
                forged_transmits=True,
            )
        ]
        content = provider.render_template(
            "esxi/portgroup.tf.j2",
            {"portgroups": portgroups, "host_alias": EsxiProvider._host_alias},
        )
        assert "promiscuous_mode = true" in content
        assert "mac_changes = false" in content
        assert "forged_transmits = true" in content


class TestVMTemplate:
    """Tests for vm.tf.j2 template."""

    def test_basic_vm(self, provider):
        """Basic VM should render with guest name and provider."""
        vms = [provider._normalize_vm_config(_make_vm())]
        content = provider.render_template(
            "esxi/vm.tf.j2",
            {"vms": vms, "host_alias": EsxiProvider._host_alias},
        )
        assert 'resource "esxi_guest"' in content
        assert "provider     = esxi.esxi_01" in content
        assert 'guest_name   = "test-vm"' in content

    def test_vm_with_resources(self, provider):
        """VM with CPU/memory should render resource fields."""
        vms = [
            provider._normalize_vm_config(
                _make_vm(numvcpus=4, memsize=8192, disk_store="datastore1")
            )
        ]
        content = provider.render_template(
            "esxi/vm.tf.j2",
            {"vms": vms, "host_alias": EsxiProvider._host_alias},
        )
        assert "numvcpus     = 4" in content
        assert "memsize      = 8192" in content
        assert 'disk_store   = "datastore1"' in content

    def test_vm_with_ovf_source(self, provider):
        """VM with OVF source should render ovf_source."""
        vms = [
            provider._normalize_vm_config(_make_vm(ovf_source="https://example.com/template.ova"))
        ]
        content = provider.render_template(
            "esxi/vm.tf.j2",
            {"vms": vms, "host_alias": EsxiProvider._host_alias},
        )
        assert 'ovf_source   = "https://example.com/template.ova"' in content

    def test_vm_with_network_interfaces(self, provider):
        """VM with network interfaces should render network blocks."""
        vms = [
            provider._normalize_vm_config(
                _make_vm(
                    network=[
                        {"portgroup": "VM Network", "nic_type": "vmxnet3"},
                        {"portgroup": "mgmt-pg", "mac_address": "AA:BB:CC:DD:EE:FF"},
                    ]
                )
            )
        ]
        content = provider.render_template(
            "esxi/vm.tf.j2",
            {"vms": vms, "host_alias": EsxiProvider._host_alias},
        )
        assert content.count("network_interfaces {") == 2
        assert '"VM Network"' in content
        assert '"vmxnet3"' in content
        assert '"mgmt-pg"' in content
        assert '"AA:BB:CC:DD:EE:FF"' in content

    def test_vm_with_virtual_disks(self, provider):
        """VM with virtual disks should render disk blocks."""
        vms = [
            provider._normalize_vm_config(
                _make_vm(
                    virtual_disks=[
                        {"virtual_disk_id": "disk1.vmdk", "slot": "0:1"},
                        {"virtual_disk_id": "disk2.vmdk", "slot": "0:2"},
                    ]
                )
            )
        ]
        content = provider.render_template(
            "esxi/vm.tf.j2",
            {"vms": vms, "host_alias": EsxiProvider._host_alias},
        )
        assert content.count("virtual_disks {") == 2
        assert '"disk1.vmdk"' in content
        assert '"0:2"' in content

    def test_vm_with_power_and_notes(self, provider):
        """VM with power state and notes should render those fields."""
        vms = [provider._normalize_vm_config(_make_vm(power="on", notes="Test VM for CI"))]
        content = provider.render_template(
            "esxi/vm.tf.j2",
            {"vms": vms, "host_alias": EsxiProvider._host_alias},
        )
        assert 'power        = "on"' in content
        assert 'notes        = "Test VM for CI"' in content

    def test_vm_single_nic_dict_normalized(self, provider):
        """Single dict NIC should be normalized to list and render."""
        vms = [provider._normalize_vm_config(_make_vm(network={"portgroup": "VM Network"}))]
        content = provider.render_template(
            "esxi/vm.tf.j2",
            {"vms": vms, "host_alias": EsxiProvider._host_alias},
        )
        assert content.count("network_interfaces {") == 1
        assert '"VM Network"' in content


class TestOutputsTemplate:
    """Tests for outputs.tf.j2 template."""

    def test_outputs_with_vms(self, provider):
        """Outputs should include VM info."""
        resources_by_type = {
            "vm": [_make_vm("web-01"), _make_vm("web-02")],
        }
        content = provider.render_template(
            "esxi/outputs.tf.j2",
            {"resources_by_type": resources_by_type},
        )
        assert "vm_info" in content
        assert "web-01" in content
        assert "web-02" in content
        assert "ip_address" in content

    def test_outputs_with_vswitches(self, provider):
        """Outputs should include vswitch names."""
        resources_by_type = {
            "vswitch": [_make_vswitch("vSwitch1"), _make_vswitch("vSwitch2")],
        }
        content = provider.render_template(
            "esxi/outputs.tf.j2",
            {"resources_by_type": resources_by_type},
        )
        assert "vswitches" in content
        assert "vSwitch1" in content
        assert "vSwitch2" in content

    def test_outputs_with_portgroups(self, provider):
        """Outputs should include portgroup names."""
        resources_by_type = {
            "portgroup": [_make_portgroup("pg-mgmt"), _make_portgroup("pg-storage")],
        }
        content = provider.render_template(
            "esxi/outputs.tf.j2",
            {"resources_by_type": resources_by_type},
        )
        assert "portgroups" in content
        assert "pg-mgmt" in content
        assert "pg-storage" in content

    def test_outputs_with_ovf_deployments(self, provider):
        """Outputs should include OVF deployment VM names."""
        resources_by_type = {
            "ovf_deployment": [
                ResourceConfig(
                    name="node-01",
                    type="ovf_deployment",
                    provider="esxi",
                    config={"vm_name": "ontap-01", "host": "esxi-01"},
                ),
                ResourceConfig(
                    name="node-02",
                    type="ovf_deployment",
                    provider="esxi",
                    config={"vm_name": "ontap-02", "host": "esxi-01"},
                ),
            ],
        }
        content = provider.render_template(
            "esxi/outputs.tf.j2",
            {"resources_by_type": resources_by_type},
        )
        assert "ovf_deployments" in content
        assert "ontap-01" in content
        assert "ontap-02" in content

    def test_outputs_ovf_deployment_defaults_to_name(self, provider):
        """OVF deployment output should fall back to resource name when vm_name missing."""
        resources_by_type = {
            "ovf_deployment": [
                ResourceConfig(
                    name="my-ovf-vm",
                    type="ovf_deployment",
                    provider="esxi",
                    config={"host": "esxi-01"},
                ),
            ],
        }
        content = provider.render_template(
            "esxi/outputs.tf.j2",
            {"resources_by_type": resources_by_type},
        )
        assert "my-ovf-vm" in content

    def test_outputs_empty_resources(self, provider):
        """Outputs with no resources should not render output blocks."""
        content = provider.render_template(
            "esxi/outputs.tf.j2",
            {"resources_by_type": {}},
        )
        assert "output" not in content
