"""Unit tests for Proxmox VM enhancement features.

Tests template rendering for cpu_type, balloon/floating, multi-NIC,
ISO boot, SATA disk, and backward compatibility.
"""

from pathlib import Path
from typing import Any

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.proxmox import ProxmoxProvider


@pytest.fixture
def provider(tmp_path: Path) -> ProxmoxProvider:
    """Create a ProxmoxProvider for template testing."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    p = ProxmoxProvider(config_dir, output_dir)
    p.set_environment("test")
    return p


def _make_vm(name: str = "test-vm", **config_overrides: Any) -> ResourceConfig:
    """Helper to create a VM ResourceConfig with sensible defaults."""
    config: dict[str, Any] = {
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

    def test_vm_with_cpu_type(self, provider: ProxmoxProvider) -> None:
        """CPU type should render in the cpu block."""
        vms = [_make_vm(cpu_type="host")]
        content = _render_vms(provider, vms)
        assert 'type    = "host"' in content

    def test_vm_cpu_type_default(self, provider: ProxmoxProvider) -> None:
        """Default cpu_type should be host."""
        vms = [_make_vm()]
        content = _render_vms(provider, vms)
        assert 'type    = "host"' in content


class TestBalloon:
    """Tests for memory balloon (floating) rendering."""

    def test_vm_with_balloon_disabled(self, provider: ProxmoxProvider) -> None:
        """Balloon=0 should render as floating = 0."""
        vms = [_make_vm(balloon=0)]
        content = _render_vms(provider, vms)
        assert "floating  = 0" in content

    def test_vm_with_balloon_value(self, provider: ProxmoxProvider) -> None:
        """Balloon with a positive value should render floating."""
        vms = [_make_vm(balloon=2048)]
        content = _render_vms(provider, vms)
        assert "floating  = 2048" in content

    def test_vm_without_balloon(self, provider: ProxmoxProvider) -> None:
        """No balloon config keeps the balloon device on, minimum = memory (#1186)."""
        vms = [_make_vm()]
        content = _render_vms(provider, vms)
        assert "dedicated = 2048" in content
        assert "floating  = 2048" in content


class TestBalloonDefaultFloating:
    """Floating defaults to dedicated for VMs and templates (#1186)."""

    @staticmethod
    def _render_template(provider: ProxmoxProvider, **cfg: Any) -> str:
        config: dict[str, Any] = {
            "name": "tpl",
            "target_node": "pve01",
            "vmid": 9000,
            "download_image": {"url": "https://x/y.img", "filename": "y.img"},
            "disk": {"storage": "local-lvm"},
            "network": {"bridge": "vmbr0"},
            **cfg,
        }
        res = ResourceConfig(name="tpl", type="template", provider="proxmox", config=config)
        return provider.render_template("proxmox/templates.tf.j2", {"templates": [res]})

    @staticmethod
    def _render_clone_template(provider: ProxmoxProvider, **cfg: Any) -> str:
        config: dict[str, Any] = {"name": "tpl", "target_node": "pve01", "vmid": 9000, **cfg}
        res = ResourceConfig(name="tpl", type="template", provider="proxmox", config=config)
        return provider.render_template("proxmox/templates.tf.j2", {"templates": [res]})

    def test_vm_unset_default_memory(self, provider: ProxmoxProvider) -> None:
        """Unset balloon and memory render 2048 for both values."""
        content = _render_vms(provider, [_make_vm()])
        assert "dedicated = 2048" in content
        assert "floating  = 2048" in content

    def test_vm_unset_explicit_memory(self, provider: ProxmoxProvider) -> None:
        """Unset balloon floats at the configured memory."""
        content = _render_vms(provider, [_make_vm(memory=14336)])
        assert "floating  = 14336" in content

    def test_vm_balloon_zero(self, provider: ProxmoxProvider) -> None:
        """Balloon 0 renders floating 0."""
        content = _render_vms(provider, [_make_vm(memory=14336, balloon=0)])
        assert "floating  = 0" in content

    def test_vm_balloon_below_memory(self, provider: ProxmoxProvider) -> None:
        """Balloon below memory renders as given."""
        content = _render_vms(provider, [_make_vm(memory=14336, balloon=8192)])
        assert "dedicated = 14336" in content
        assert "floating  = 8192" in content

    @pytest.mark.parametrize("render", ["_render_template", "_render_clone_template"])
    def test_template_unset_default_memory(self, provider: ProxmoxProvider, render: str) -> None:
        """Template without balloon or memory floats at 2048."""
        content = getattr(self, render)(provider)
        assert "floating  = 2048" in content
        assert content.count("floating") == content.count("memory {")

    @pytest.mark.parametrize("render", ["_render_template", "_render_clone_template"])
    def test_template_unset_explicit_memory(self, provider: ProxmoxProvider, render: str) -> None:
        """Template without balloon floats at its memory."""
        content = getattr(self, render)(provider, memory=14336)
        assert "floating  = 14336" in content

    @pytest.mark.parametrize("render", ["_render_template", "_render_clone_template"])
    def test_template_balloon_zero(self, provider: ProxmoxProvider, render: str) -> None:
        """Template balloon 0 renders floating 0."""
        content = getattr(self, render)(provider, memory=14336, balloon=0)
        assert "floating  = 0" in content

    @pytest.mark.parametrize("render", ["_render_template", "_render_clone_template"])
    def test_template_balloon_below_memory(self, provider: ProxmoxProvider, render: str) -> None:
        """Template balloon below memory renders as given."""
        content = getattr(self, render)(provider, memory=14336, balloon=8192)
        assert "floating  = 8192" in content


class TestMultiNIC:
    """Tests for multi-NIC support."""

    def test_vm_with_multi_nic(self, provider: ProxmoxProvider) -> None:
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

    def test_vm_with_single_nic_backward_compat(self, provider: ProxmoxProvider) -> None:
        """A single dict network config should still render correctly after normalization."""
        vms = [_make_vm(network={"bridge": "vmbr0", "tag": 50})]
        content = _render_vms(provider, vms)
        assert content.count("network_device {") == 1
        assert '"vmbr0"' in content
        assert "vlan_id     = 50" in content

    def test_vm_with_nic_mac_address(self, provider: ProxmoxProvider) -> None:
        """MAC address should render in network_device."""
        vms = [_make_vm(network=[{"bridge": "vmbr0", "macaddr": "AA:BB:CC:DD:EE:FF"}])]
        content = _render_vms(provider, vms)
        assert '"AA:BB:CC:DD:EE:FF"' in content

    def test_vm_with_nic_model(self, provider: ProxmoxProvider) -> None:
        """NIC model should render in network_device."""
        vms = [_make_vm(network=[{"bridge": "vmbr0", "model": "e1000"}])]
        content = _render_vms(provider, vms)
        assert 'model       = "e1000"' in content


class TestISOBoot:
    """Tests for ISO boot / cdrom support."""

    def test_vm_with_iso_boot(self, provider: ProxmoxProvider) -> None:
        """ISO config should render a cdrom block with file_id."""
        vms = [_make_vm(iso="local:iso/ubuntu-24.04.iso")]
        content = _render_vms(provider, vms)
        assert "cdrom {" in content
        assert 'file_id = "local:iso/ubuntu-24.04.iso"' in content

    def test_vm_without_iso(self, provider: ProxmoxProvider) -> None:
        """No ISO should omit the cdrom block."""
        vms = [_make_vm()]
        content = _render_vms(provider, vms)
        assert "cdrom" not in content

    def test_vm_iso_skips_initialization(self, provider: ProxmoxProvider) -> None:
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

    def test_vm_with_sata_disk(self, provider: ProxmoxProvider) -> None:
        """SATA disk type should render as interface = 'sata0'."""
        vms = [_make_vm(disk={"storage": "local-lvm", "size": "50G", "type": "sata"})]
        content = _render_vms(provider, vms)
        assert '"sata0"' in content

    def test_vm_with_scsi_disk(self, provider: ProxmoxProvider) -> None:
        """SCSI disk type should still render as interface = 'scsi0'."""
        vms = [_make_vm(disk={"storage": "local-lvm", "size": "50G", "type": "scsi"})]
        content = _render_vms(provider, vms)
        assert '"scsi0"' in content

    def test_vm_with_virtio_disk(self, provider: ProxmoxProvider) -> None:
        """Virtio disk type should render as interface = 'virtio0'."""
        vms = [_make_vm(disk={"storage": "local-lvm", "size": "50G", "type": "virtio"})]
        content = _render_vms(provider, vms)
        assert '"virtio0"' in content


class TestAllNewFields:
    """Integration test with all new features together."""

    def test_vm_with_all_new_fields(self, provider: ProxmoxProvider) -> None:
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

    def test_vm_with_boot_order(self, provider: ProxmoxProvider) -> None:
        """Boot order should render as a list."""
        vms = [_make_vm(boot_order=["sata0", "ide3"])]
        content = _render_vms(provider, vms)
        assert "boot_order" in content
        assert '"sata0"' in content
        assert '"ide3"' in content

    def test_vm_without_boot_order(self, provider: ProxmoxProvider) -> None:
        """No boot_order config should not render the attribute."""
        vms = [_make_vm(clone="100")]
        content = _render_vms(provider, vms)
        assert "boot_order" not in content

    def test_vm_single_boot_device(self, provider: ProxmoxProvider) -> None:
        """Single device boot order should render correctly."""
        vms = [_make_vm(boot_order=["scsi0"])]
        content = _render_vms(provider, vms)
        assert "boot_order" in content
        assert '"scsi0"' in content


class TestClone:
    """Tests for VM clone block rendering, including cross-node cloning."""

    def test_clone_scalar(self, provider: ProxmoxProvider) -> None:
        """Scalar clone value should be normalized to dict and render vm_id."""
        vms = [_make_vm(clone=100)]
        content = _render_vms(provider, vms)
        assert "vm_id = 100" in content
        # clone block should not contain node_name (top-level node_name is for the VM itself)
        clone_block = content.split("clone {")[1].split("}")[0]
        assert "node_name" not in clone_block
        assert "datastore_id" not in clone_block

    def test_clone_dict_vm_id_only(self, provider: ProxmoxProvider) -> None:
        """Dict clone with only vm_id should render vm_id without node_name."""
        vms = [_make_vm(clone={"vm_id": 901})]
        content = _render_vms(provider, vms)
        assert "vm_id = 901" in content
        clone_block = content.split("clone {")[1].split("}")[0]
        assert "node_name" not in clone_block

    def test_clone_cross_node(self, provider: ProxmoxProvider) -> None:
        """Dict clone with node_name should render both vm_id and node_name."""
        vms = [_make_vm(clone={"vm_id": 901, "node_name": "pve1"})]
        content = _render_vms(provider, vms)
        assert "vm_id = 901" in content
        assert 'node_name    = "pve1"' in content

    def test_clone_cross_node_with_datastore(self, provider: ProxmoxProvider) -> None:
        """Dict clone with node_name and datastore_id should render all fields."""
        vms = [_make_vm(clone={"vm_id": 901, "node_name": "pve1", "datastore_id": "local-lvm"})]
        content = _render_vms(provider, vms)
        assert "vm_id = 901" in content
        assert 'node_name    = "pve1"' in content
        assert 'datastore_id = "local-lvm"' in content

    def test_clone_with_full_clone(self, provider: ProxmoxProvider) -> None:
        """Clone with full_clone should render the full field."""
        vms = [_make_vm(clone={"vm_id": 901, "node_name": "pve1"}, full_clone=True)]
        content = _render_vms(provider, vms)
        assert "vm_id = 901" in content
        assert 'node_name    = "pve1"' in content
        assert "full = true" in content

    def test_clone_string_vmid_normalized(self, provider: ProxmoxProvider) -> None:
        """String clone value should be normalized to dict."""
        vms = [_make_vm(clone="901")]
        content = _render_vms(provider, vms)
        assert "vm_id = 901" in content


class TestDefaultsUnchanged:
    """Verify that minimal configs still produce the same output."""

    def test_vm_defaults_unchanged(self, provider: ProxmoxProvider) -> None:
        """A minimal VM config should produce default values with no new blocks."""
        vms = [_make_vm(clone="100")]
        content = _render_vms(provider, vms)
        assert 'type    = "host"' in content
        assert "dedicated = 2048" in content
        assert "floating  = 2048" in content  # balloon on, minimum = memory (#1186)
        assert "cdrom" not in content
        assert "network_device" not in content  # No network defined


class TestNormalization:
    """Tests for _normalize_vm_config()."""

    def test_normalize_dict_to_list(self, provider: ProxmoxProvider) -> None:
        """Single dict network should be wrapped in a list."""
        vm = _make_vm(network={"bridge": "vmbr0"})
        result = provider._normalize_vm_config(vm)
        assert isinstance(result.config["network"], list)
        assert len(result.config["network"]) == 1
        assert result.config["network"][0]["bridge"] == "vmbr0"

    def test_normalize_list_unchanged(self, provider: ProxmoxProvider) -> None:
        """List network should remain a list."""
        nics = [{"bridge": "vmbr0"}, {"bridge": "vmbr1"}]
        vm = _make_vm(network=nics)
        result = provider._normalize_vm_config(vm)
        assert isinstance(result.config["network"], list)
        assert len(result.config["network"]) == 2

    def test_normalize_no_network(self, provider: ProxmoxProvider) -> None:
        """No network key should remain absent."""
        vm = _make_vm()
        result = provider._normalize_vm_config(vm)
        assert "network" not in result.config

    def test_normalize_does_not_mutate_original(self, provider: ProxmoxProvider) -> None:
        """Original VM config should not be modified."""
        vm = _make_vm(network={"bridge": "vmbr0"})
        provider._normalize_vm_config(vm)
        # Original should still be a dict
        assert isinstance(vm.config["network"], dict)

    def test_normalize_clone_scalar_to_dict(self, provider: ProxmoxProvider) -> None:
        """Scalar clone should be normalized to dict with vm_id key."""
        vm = _make_vm(clone=901)
        result = provider._normalize_vm_config(vm)
        assert isinstance(result.config["clone"], dict)
        assert result.config["clone"]["vm_id"] == 901

    def test_normalize_clone_string_to_dict(self, provider: ProxmoxProvider) -> None:
        """String clone should be normalized to dict with vm_id key."""
        vm = _make_vm(clone="901")
        result = provider._normalize_vm_config(vm)
        assert isinstance(result.config["clone"], dict)
        assert result.config["clone"]["vm_id"] == "901"

    def test_normalize_clone_dict_unchanged(self, provider: ProxmoxProvider) -> None:
        """Dict clone should remain unchanged."""
        vm = _make_vm(clone={"vm_id": 901, "node_name": "pve1"})
        result = provider._normalize_vm_config(vm)
        assert isinstance(result.config["clone"], dict)
        assert result.config["clone"]["vm_id"] == 901
        assert result.config["clone"]["node_name"] == "pve1"

    def test_normalize_clone_does_not_mutate_original(self, provider: ProxmoxProvider) -> None:
        """Original clone scalar should not be modified."""
        vm = _make_vm(clone=901)
        provider._normalize_vm_config(vm)
        assert vm.config["clone"] == 901
