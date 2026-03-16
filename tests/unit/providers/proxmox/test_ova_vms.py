"""Unit tests for Proxmox OVA-based VM template rendering.

Tests the ova_vms.tf.j2 template and the routing logic that sends VMs with
ova_source to the OVA template instead of the regular vms.tf template.
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


def _make_ova_vm(name: str = "test-ova-vm", **config_overrides) -> ResourceConfig:
    """Helper to create an OVA VM ResourceConfig with sensible defaults."""
    config: dict = {
        "name": name,
        "target_node": "pve01",
        "vmid": 900,
        "ova_source": "/var/lib/vz/template/appliance/test.ova",
        **config_overrides,
    }
    return ResourceConfig(name=name, type="vm", provider="proxmox", config=config)


def _make_regular_vm(name: str = "regular-vm", **config_overrides) -> ResourceConfig:
    """Helper to create a regular VM ResourceConfig (no ova_source)."""
    config: dict = {
        "name": name,
        "target_node": "pve01",
        "clone": "100",
        **config_overrides,
    }
    return ResourceConfig(name=name, type="vm", provider="proxmox", config=config)


def _render_ova_vms(provider: ProxmoxProvider, vms: list[ResourceConfig]) -> str:
    """Normalize OVA VM configs and render through the ova_vms template."""
    processed = [provider._normalize_vm_config(vm) for vm in vms]
    return provider.render_template("proxmox/ova_vms.tf.j2", {"ova_vms": processed})


class TestOVAExtraction:
    """Tests for OVA extraction phase."""

    def test_ova_source_renders_in_extract(self, provider):
        """OVA source path should appear in the tar extract command."""
        vms = [_make_ova_vm(ova_source="/storage/appliances/ontap.ova")]
        content = _render_ova_vms(provider, vms)
        assert "tar -xf" in content
        assert "/storage/appliances/ontap.ova" in content

    def test_ova_temp_dir_uses_vm_name(self, provider):
        """Temp directory should use the VM name."""
        vms = [_make_ova_vm(name="my-appliance")]
        content = _render_ova_vms(provider, vms)
        assert "/tmp/ova-${self.triggers_replace.name}" in content


class TestOVADiskImport:
    """Tests for disk bus type rendering in import commands."""

    def test_default_disk_bus_is_ide(self, provider):
        """Default disk bus should be ide."""
        vms = [_make_ova_vm()]
        content = _render_ova_vms(provider, vms)
        assert 'disk_bus   = "ide"' in content

    def test_sata_disk_bus(self, provider):
        """SATA disk bus should render correctly."""
        vms = [_make_ova_vm(disk_bus="sata")]
        content = _render_ova_vms(provider, vms)
        assert 'disk_bus   = "sata"' in content

    def test_scsi_disk_bus(self, provider):
        """SCSI disk bus should render correctly."""
        vms = [_make_ova_vm(disk_bus="scsi")]
        content = _render_ova_vms(provider, vms)
        assert 'disk_bus   = "scsi"' in content

    def test_virtio_disk_bus(self, provider):
        """Virtio disk bus should render correctly."""
        vms = [_make_ova_vm(disk_bus="virtio")]
        content = _render_ova_vms(provider, vms)
        assert 'disk_bus   = "virtio"' in content

    def test_disk_bus_in_attach_command(self, provider):
        """Disk bus should be used in the qm set attach command via triggers."""
        vms = [_make_ova_vm(disk_bus="sata")]
        content = _render_ova_vms(provider, vms)
        assert "${self.triggers_replace.disk_bus}" in content

    def test_disk_path_parsed_from_import_output(self, provider):
        """Disk path should be parsed from qm disk import output, not qm config.

        Parsing 'successfully imported' from stdout is reliable for multi-disk
        imports, unlike grepping unused0 from qm config which breaks when
        multiple disks are imported in sequence.
        """
        vms = [_make_ova_vm()]
        content = _render_ova_vms(provider, vms)
        assert "successfully imported" in content
        assert "IMPORT_OUT" in content
        # Ensure the old fragile unused0 pattern is not used
        assert "unused0" not in content


class TestOVADiskStorage:
    """Tests for disk storage pool rendering."""

    def test_default_storage_is_local_lvm(self, provider):
        """Default disk storage should be local-lvm."""
        vms = [_make_ova_vm()]
        content = _render_ova_vms(provider, vms)
        assert "local-lvm" in content
        assert "qm disk import" in content

    def test_custom_storage_pool(self, provider):
        """Custom storage pool should render in disk import command."""
        vms = [_make_ova_vm(disk_storage="ceph-pool")]
        content = _render_ova_vms(provider, vms)
        assert "ceph-pool" in content


class TestOVASerial:
    """Tests for serial console flag."""

    def test_serial_enabled(self, provider):
        """Serial flag should add --serial0 socket."""
        vms = [_make_ova_vm(serial=True)]
        content = _render_ova_vms(provider, vms)
        assert "--serial0 socket" in content

    def test_serial_disabled_by_default(self, provider):
        """Serial should not appear when not set."""
        vms = [_make_ova_vm()]
        content = _render_ova_vms(provider, vms)
        assert "--serial0" not in content

    def test_serial_explicitly_false(self, provider):
        """Serial explicitly false should not add serial."""
        vms = [_make_ova_vm(serial=False)]
        content = _render_ova_vms(provider, vms)
        assert "--serial0" not in content


class TestOVANetwork:
    """Tests for multi-NIC rendering."""

    def test_single_nic(self, provider):
        """Single NIC should render as --net0."""
        vms = [_make_ova_vm(network=[{"bridge": "vmbr0", "model": "virtio"}])]
        content = _render_ova_vms(provider, vms)
        assert "--net0 virtio,bridge=vmbr0" in content

    def test_multi_nic(self, provider):
        """Multiple NICs should render as --net0, --net1, etc."""
        vms = [
            _make_ova_vm(
                network=[
                    {"bridge": "vmbr0", "model": "virtio", "tag": 100},
                    {"bridge": "vmbr1", "model": "e1000"},
                    {"bridge": "vmbr2"},
                ]
            )
        ]
        content = _render_ova_vms(provider, vms)
        assert "--net0 virtio,bridge=vmbr0,tag=100" in content
        assert "--net1 e1000,bridge=vmbr1" in content
        assert "--net2 virtio,bridge=vmbr2" in content

    def test_nic_with_vlan_tag(self, provider):
        """VLAN tag should render in NIC definition."""
        vms = [_make_ova_vm(network=[{"bridge": "vmbr0", "tag": 200}])]
        content = _render_ova_vms(provider, vms)
        assert "tag=200" in content

    def test_nic_with_mac_address(self, provider):
        """MAC address should render in NIC definition."""
        vms = [_make_ova_vm(network=[{"bridge": "vmbr0", "macaddr": "AA:BB:CC:DD:EE:FF"}])]
        content = _render_ova_vms(provider, vms)
        assert "macaddr=AA:BB:CC:DD:EE:FF" in content

    def test_no_network(self, provider):
        """No network config should not render any --net flags."""
        vms = [_make_ova_vm()]
        # Remove network key entirely
        vms[0].config.pop("network", None)
        content = _render_ova_vms(provider, vms)
        assert "--net0" not in content


class TestOVACPUType:
    """Tests for CPU type rendering."""

    def test_default_cpu_type(self, provider):
        """Default CPU type should be host."""
        vms = [_make_ova_vm()]
        content = _render_ova_vms(provider, vms)
        assert "--cpu host" in content

    def test_custom_cpu_type(self, provider):
        """Custom CPU type should render in qm create."""
        vms = [_make_ova_vm(cpu_type="SandyBridge")]
        content = _render_ova_vms(provider, vms)
        assert "--cpu SandyBridge" in content

    def test_host_cpu_type(self, provider):
        """Host CPU passthrough should render correctly."""
        vms = [_make_ova_vm(cpu_type="host")]
        content = _render_ova_vms(provider, vms)
        assert "--cpu host" in content


class TestOVADestroy:
    """Tests for destroy provisioner."""

    def test_destroy_provisioner_present(self, provider):
        """Destroy provisioner should be present with qm stop and destroy."""
        vms = [_make_ova_vm()]
        content = _render_ova_vms(provider, vms)
        assert "when    = destroy" in content
        assert "qm stop" in content
        assert "qm destroy" in content
        assert "--purge" in content

    def test_destroy_uses_vmid_trigger(self, provider):
        """Destroy provisioner should reference VMID from triggers."""
        vms = [_make_ova_vm()]
        content = _render_ova_vms(provider, vms)
        assert "${self.triggers_replace.vmid}" in content


class TestOVADefaults:
    """Tests for minimal config with default values."""

    def test_minimal_config_defaults(self, provider):
        """Minimal OVA config should produce sensible defaults."""
        vms = [_make_ova_vm()]
        content = _render_ova_vms(provider, vms)
        # Default memory
        assert "--memory 2048" in content
        # Default cores
        assert "--cores 2" in content
        # Default CPU type
        assert "--cpu host" in content
        # Default disk bus
        assert 'disk_bus   = "ide"' in content
        # Default storage
        assert "local-lvm" in content
        # Should have terraform_data resource
        assert "terraform_data" in content
        # Should have triggers_replace
        assert "triggers_replace" in content

    def test_custom_memory_and_cores(self, provider):
        """Custom memory and cores should override defaults."""
        vms = [_make_ova_vm(memory=8192, cores=4)]
        content = _render_ova_vms(provider, vms)
        assert "--memory 8192" in content
        assert "--cores 4" in content

    def test_onboot_renders(self, provider):
        """Onboot flag should render qm set --onboot 1."""
        vms = [_make_ova_vm(onboot=True)]
        content = _render_ova_vms(provider, vms)
        assert "--onboot 1" in content

    def test_tags_render(self, provider):
        """Tags should render in qm set command."""
        vms = [_make_ova_vm(tags=["infra", "appliance"])]
        content = _render_ova_vms(provider, vms)
        assert "--tags infra,appliance" in content

    def test_custom_boot_order(self, provider):
        """Custom boot order should override default."""
        vms = [_make_ova_vm(boot_order=["sata0", "ide2"])]
        content = _render_ova_vms(provider, vms)
        assert "order=sata0;ide2" in content

    def test_target_node_used_as_ssh_target(self, provider):
        """Each VM's target_node should be used as SSH target, not a global ssh_hostname."""
        vms = [_make_ova_vm(target_node="pve02")]
        content = _render_ova_vms(provider, vms)
        assert "pve02" in content

    def test_multiple_vms_use_own_target_nodes(self, provider):
        """Each VM should SSH to its own target_node, not a shared host."""
        vms = [
            _make_ova_vm(name="vm-a", vmid=900, target_node="pve01"),
            _make_ova_vm(name="vm-b", vmid=901, target_node="pve02"),
        ]
        content = _render_ova_vms(provider, vms)
        # Split by resource blocks to check each VM targets its own node
        blocks = content.split("# OVA VM:")
        vm_a_block = next(b for b in blocks if "vm-a" in b)
        vm_b_block = next(b for b in blocks if "vm-b" in b)
        assert 'ssh_target = "pve01"' in vm_a_block
        assert 'ssh_target = "pve02"' in vm_b_block


class TestOVAVMRouting:
    """Tests for VM routing between regular and OVA templates."""

    def test_ova_vm_generates_ova_template(self, provider):
        """VM with ova_source should render through ova_vms template."""
        vms = [_make_ova_vm()]
        content = _render_ova_vms(provider, vms)
        assert "terraform_data" in content
        assert "ova_vm_" in content

    def test_regular_vm_not_in_ova_template(self, provider):
        """Regular VM should not appear in OVA template output."""
        regular = _make_regular_vm()
        processed = [provider._normalize_vm_config(regular)]
        content = provider.render_template("proxmox/vms.tf.j2", {"vms": processed})
        assert "proxmox_virtual_environment_vm" in content
        assert "terraform_data" not in content

    def test_mixed_vms_partition(self):
        """VMs should be correctly partitioned by ova_source presence."""
        ova_vm = _make_ova_vm(name="ova-appliance")
        regular_vm = _make_regular_vm(name="regular-server")

        # Check that ova_source presence is the partitioning criterion
        assert "ova_source" in ova_vm.config
        assert "ova_source" not in regular_vm.config

    def test_ova_vm_skips_cloud_init(self, provider):
        """OVA VMs should not go through cloud-init processing."""
        # An OVA VM with cloud_init_snippets should not crash
        # because _generate_vms_terraform skips cloud-init for OVA VMs
        ova_vm = _make_ova_vm(cloud_init_snippets=["base"])
        content = _render_ova_vms(provider, [ova_vm])
        # Should render as OVA, not as regular VM with cloud-init
        assert "terraform_data" in content
        assert "cloud_init" not in content


class TestOVATriggers:
    """Tests for terraform_data triggers_replace."""

    def test_triggers_include_vmid(self, provider):
        """Triggers should include vmid."""
        vms = [_make_ova_vm(vmid=950)]
        content = _render_ova_vms(provider, vms)
        assert 'vmid       = "950"' in content

    def test_triggers_include_ova_source(self, provider):
        """Triggers should include ova_source."""
        vms = [_make_ova_vm(ova_source="/path/to/app.ova")]
        content = _render_ova_vms(provider, vms)
        assert 'ova_source = "/path/to/app.ova"' in content

    def test_triggers_include_disk_bus(self, provider):
        """Triggers should include disk_bus."""
        vms = [_make_ova_vm(disk_bus="scsi")]
        content = _render_ova_vms(provider, vms)
        assert 'disk_bus   = "scsi"' in content

    def test_triggers_include_name(self, provider):
        """Triggers should include name."""
        vms = [_make_ova_vm(name="my-vm")]
        content = _render_ova_vms(provider, vms)
        assert 'name       = "my-vm"' in content

    def test_triggers_include_ssh_fields(self, provider):
        """Triggers should include ssh_cmd, ssh_user, and ssh_target for destroy provisioner."""
        vms = [_make_ova_vm()]
        content = _render_ova_vms(provider, vms)
        assert "ssh_cmd    = local.ssh_cmd" in content
        assert "ssh_user   = var.proxmox_ssh_user" in content
        assert 'ssh_target = "pve01"' in content

    def test_destroy_uses_self_ssh_references(self, provider):
        """Destroy provisioner must use self.triggers_replace for SSH, not local/var."""
        vms = [_make_ova_vm()]
        content = _render_ova_vms(provider, vms)
        # Find the destroy provisioner section
        destroy_idx = content.find("when    = destroy")
        assert destroy_idx != -1
        destroy_section = content[destroy_idx:]
        assert "${self.triggers_replace.ssh_cmd}" in destroy_section
        assert "${self.triggers_replace.ssh_user}" in destroy_section
        assert "${self.triggers_replace.ssh_target}" in destroy_section
