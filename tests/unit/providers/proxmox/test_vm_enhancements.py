"""Unit tests for Proxmox VM enhancement features.

Tests template rendering for cpu_type, balloon/floating, multi-NIC,
ISO boot, SATA disk, and backward compatibility.
"""

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.proxmox import ProxmoxProvider


@pytest.fixture
def provider(tmp_path):
    """Create a ProxmoxProvider for template testing."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    p = ProxmoxProvider(config_dir, output_dir)
    p.set_environment("test")
    return p


def _make_vm(name: str = "test-vm", **config_overrides) -> ResourceConfig:
    """Helper to create a VM ResourceConfig with sensible defaults."""
    config: dict = {
        "name": name,
        "target_node": "pve01",
        **config_overrides,
    }
    return ResourceConfig(name=name, type="vm", provider="proxmox", config=config)


def _render_vms(provider: ProxmoxProvider, vms: list[ResourceConfig]) -> str:
    """Normalize VM configs and render through the template."""
    processed = [provider._normalize_vm_config(vm) for vm in vms]
    return provider.render_template("proxmox/vms.tf.j2", {"vms": processed})


class TestCPUType:
    """Tests for cpu_type rendering in the cpu block."""

    def test_vm_with_cpu_type(self, provider):
        """CPU type should render in the cpu block."""
        vms = [_make_vm(cpu_type="host")]
        content = _render_vms(provider, vms)
        assert 'type    = "host"' in content

    def test_vm_cpu_type_default(self, provider):
        """Default cpu_type should be kvm64."""
        vms = [_make_vm()]
        content = _render_vms(provider, vms)
        assert 'type    = "kvm64"' in content


class TestBalloon:
    """Tests for memory balloon (floating) rendering."""

    def test_vm_with_balloon_disabled(self, provider):
        """Balloon=0 should render as floating = 0."""
        vms = [_make_vm(balloon=0)]
        content = _render_vms(provider, vms)
        assert "floating  = 0" in content

    def test_vm_with_balloon_value(self, provider):
        """Balloon with a positive value should render floating."""
        vms = [_make_vm(balloon=2048)]
        content = _render_vms(provider, vms)
        assert "floating  = 2048" in content

    def test_vm_without_balloon(self, provider):
        """No balloon config should omit the floating attribute."""
        vms = [_make_vm()]
        content = _render_vms(provider, vms)
        assert "floating" not in content


class TestMultiNIC:
    """Tests for multi-NIC support."""

    def test_vm_with_multi_nic(self, provider):
        """Multiple NICs should produce multiple network_device blocks."""
        vms = [
            _make_vm(
                network=[
                    {"bridge": "vmbr0", "model": "virtio", "tag": 100},
                    {"bridge": "vmbr1", "model": "e1000e", "tag": 200},
                    {"bridge": "vmbr2", "model": "vmxnet3"},
                ]
            )
        ]
        content = _render_vms(provider, vms)
        assert content.count("network_device {") == 3
        assert '"virtio"' in content
        assert '"e1000e"' in content
        assert '"vmxnet3"' in content
        assert "vlan_id     = 100" in content
        assert "vlan_id     = 200" in content

    def test_vm_with_single_nic_backward_compat(self, provider):
        """A single dict network config should still render correctly after normalization."""
        vms = [_make_vm(network={"bridge": "vmbr0", "tag": 50})]
        content = _render_vms(provider, vms)
        assert content.count("network_device {") == 1
        assert '"vmbr0"' in content
        assert "vlan_id     = 50" in content

    def test_vm_with_nic_mac_address(self, provider):
        """MAC address should render in network_device."""
        vms = [_make_vm(network=[{"bridge": "vmbr0", "macaddr": "AA:BB:CC:DD:EE:FF"}])]
        content = _render_vms(provider, vms)
        assert '"AA:BB:CC:DD:EE:FF"' in content

    def test_vm_with_nic_model(self, provider):
        """NIC model should render in network_device."""
        vms = [_make_vm(network=[{"bridge": "vmbr0", "model": "e1000"}])]
        content = _render_vms(provider, vms)
        assert 'model       = "e1000"' in content


class TestISOBoot:
    """Tests for ISO boot / cdrom support."""

    def test_vm_with_iso_boot(self, provider):
        """ISO config should render a cdrom block with file_id."""
        vms = [_make_vm(iso="local:iso/ubuntu-24.04.iso")]
        content = _render_vms(provider, vms)
        assert "cdrom {" in content
        assert 'file_id = "local:iso/ubuntu-24.04.iso"' in content

    def test_vm_without_iso(self, provider):
        """No ISO should omit the cdrom block."""
        vms = [_make_vm()]
        content = _render_vms(provider, vms)
        assert "cdrom" not in content

    def test_vm_iso_skips_initialization(self, provider):
        """When ISO is set, cloud-init initialization block should be skipped."""
        vms = [
            _make_vm(
                iso="local:iso/ubuntu-24.04.iso",
                ipconfig="ip=192.168.1.10/24,gw=192.168.1.1",
                ssh_user="ubuntu",
            )
        ]
        content = _render_vms(provider, vms)
        assert "initialization {" not in content
        assert "cdrom {" in content


class TestSATADisk:
    """Tests for SATA disk type support."""

    def test_vm_with_sata_disk(self, provider):
        """SATA disk type should render as interface = 'sata0'."""
        vms = [_make_vm(disk={"storage": "local-lvm", "size": "50G", "type": "sata"})]
        content = _render_vms(provider, vms)
        assert '"sata0"' in content

    def test_vm_with_scsi_disk(self, provider):
        """SCSI disk type should still render as interface = 'scsi0'."""
        vms = [_make_vm(disk={"storage": "local-lvm", "size": "50G", "type": "scsi"})]
        content = _render_vms(provider, vms)
        assert '"scsi0"' in content

    def test_vm_with_virtio_disk(self, provider):
        """Virtio disk type should render as interface = 'virtio0'."""
        vms = [_make_vm(disk={"storage": "local-lvm", "size": "50G", "type": "virtio"})]
        content = _render_vms(provider, vms)
        assert '"virtio0"' in content


class TestAllNewFields:
    """Integration test with all new features together."""

    def test_vm_with_all_new_fields(self, provider):
        """A VM with all new fields should render them all correctly."""
        vms = [
            _make_vm(
                cpu_type="host",
                machine="q35",
                bios="ovmf",
                balloon=0,
                cores=8,
                memory=32768,
                disk={"storage": "local-lvm", "size": "100G", "type": "sata"},
                efi_disk={"storage": "local-lvm"},
                network=[
                    {"bridge": "vmbr0", "model": "vmxnet3", "tag": 100},
                    {"bridge": "vmbr1", "model": "vmxnet3", "tag": 200},
                ],
            )
        ]
        content = _render_vms(provider, vms)
        assert 'type    = "host"' in content
        assert 'machine = "q35"' in content
        assert 'bios = "ovmf"' in content
        assert "floating  = 0" in content
        assert '"sata0"' in content
        assert content.count("network_device {") == 2
        assert "efi_disk {" in content


class TestBootOrder:
    """Tests for boot_order rendering."""

    def test_vm_with_boot_order(self, provider):
        """Boot order should render as a list."""
        vms = [_make_vm(boot_order=["sata0", "ide3"])]
        content = _render_vms(provider, vms)
        assert "boot_order" in content
        assert '"sata0"' in content
        assert '"ide3"' in content

    def test_vm_without_boot_order(self, provider):
        """No boot_order config should not render the attribute."""
        vms = [_make_vm(clone="100")]
        content = _render_vms(provider, vms)
        assert "boot_order" not in content

    def test_vm_single_boot_device(self, provider):
        """Single device boot order should render correctly."""
        vms = [_make_vm(boot_order=["scsi0"])]
        content = _render_vms(provider, vms)
        assert "boot_order" in content
        assert '"scsi0"' in content


class TestDefaultsUnchanged:
    """Verify that minimal configs still produce the same output."""

    def test_vm_defaults_unchanged(self, provider):
        """A minimal VM config should produce default values with no new blocks."""
        vms = [_make_vm(clone="100")]
        content = _render_vms(provider, vms)
        assert 'type    = "kvm64"' in content
        assert "floating" not in content
        assert "cdrom" not in content
        assert "network_device" not in content  # No network defined


class TestNormalization:
    """Tests for _normalize_vm_config()."""

    def test_normalize_dict_to_list(self, provider):
        """Single dict network should be wrapped in a list."""
        vm = _make_vm(network={"bridge": "vmbr0"})
        result = provider._normalize_vm_config(vm)
        assert isinstance(result.config["network"], list)
        assert len(result.config["network"]) == 1
        assert result.config["network"][0]["bridge"] == "vmbr0"

    def test_normalize_list_unchanged(self, provider):
        """List network should remain a list."""
        nics = [{"bridge": "vmbr0"}, {"bridge": "vmbr1"}]
        vm = _make_vm(network=nics)
        result = provider._normalize_vm_config(vm)
        assert isinstance(result.config["network"], list)
        assert len(result.config["network"]) == 2

    def test_normalize_no_network(self, provider):
        """No network key should remain absent."""
        vm = _make_vm()
        result = provider._normalize_vm_config(vm)
        assert "network" not in result.config

    def test_normalize_does_not_mutate_original(self, provider):
        """Original VM config should not be modified."""
        vm = _make_vm(network={"bridge": "vmbr0"})
        provider._normalize_vm_config(vm)
        # Original should still be a dict
        assert isinstance(vm.config["network"], dict)
