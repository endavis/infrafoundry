"""Unit tests for Proxmox LXC container support.

Tests template rendering, config normalization, resource type registration,
and dependency resolution for LXC containers.
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


def _make_ct(name: str = "test-ct", **config_overrides) -> ResourceConfig:
    """Helper to create a container ResourceConfig with sensible defaults."""
    config: dict = {
        "name": name,
        "target_node": "pve01",
        **config_overrides,
    }
    return ResourceConfig(name=name, type="container", provider="proxmox", config=config)


def _render_containers(provider: ProxmoxProvider, containers: list[ResourceConfig]) -> str:
    """Normalize container configs and render through the template."""
    processed = [provider._normalize_container_config(ct) for ct in containers]
    return provider.render_template("proxmox/containers.tf.j2", {"containers": processed})


class TestResourceRegistration:
    """Tests for container resource type registration."""

    def test_resource_types_include_container(self, provider):
        """Container should be in the list of supported resource types."""
        types = provider.get_resource_types()
        assert "container" in types

    def test_dependencies_include_container(self, provider):
        """Container dependencies should include network."""
        deps = provider.get_dependencies()
        assert "container" in deps
        assert "network" in deps["container"]

    def test_existing_types_still_present(self, provider):
        """Existing resource types should still be registered."""
        types = provider.get_resource_types()
        assert "vm" in types
        assert "template" in types
        assert "network" in types


class TestBasicContainerRendering:
    """Tests for basic container template rendering."""

    def test_basic_container(self, provider):
        """A basic container should render the correct Terraform resource."""
        containers = [
            _make_ct(
                ostemplate="nas01:vztmpl/alpine-3.21.tar.xz",
                ostype="alpine",
                cores=1,
                memory=64,
            )
        ]
        content = _render_containers(provider, containers)
        assert 'resource "proxmox_virtual_environment_container"' in content
        assert 'node_name   = "pve01"' in content
        assert 'template_file_id = "nas01:vztmpl/alpine-3.21.tar.xz"' in content
        assert 'type             = "alpine"' in content
        assert "cores        = 1" in content
        assert "dedicated = 64" in content

    def test_container_with_ctid(self, provider):
        """Container with ctid should render vm_id."""
        containers = [_make_ct(ostemplate="s:vztmpl/t.tar.xz", ctid=300)]
        content = _render_containers(provider, containers)
        assert "vm_id       = 300" in content

    def test_container_unprivileged(self, provider):
        """Unprivileged flag should render correctly."""
        containers = [_make_ct(ostemplate="s:vztmpl/t.tar.xz", unprivileged=True)]
        content = _render_containers(provider, containers)
        assert "unprivileged = true" in content

    def test_container_started_and_onboot(self, provider):
        """Started and start_on_boot should render correctly."""
        containers = [_make_ct(ostemplate="s:vztmpl/t.tar.xz", start=True, onboot=True)]
        content = _render_containers(provider, containers)
        assert "started     = true" in content
        assert "start_on_boot = true" in content

    def test_container_tags(self, provider):
        """Tags should render as a JSON array."""
        containers = [_make_ct(ostemplate="s:vztmpl/t.tar.xz", tags=["web", "infra"])]
        content = _render_containers(provider, containers)
        assert '["web", "infra"]' in content

    def test_container_description(self, provider):
        """Description should render correctly."""
        containers = [_make_ct(ostemplate="s:vztmpl/t.tar.xz", description="Test container")]
        content = _render_containers(provider, containers)
        assert 'description = "Test container"' in content

    def test_container_name_with_dashes(self, provider):
        """Container name with dashes should be converted to underscores in resource ID."""
        containers = [_make_ct(name="web-server-01", ostemplate="s:vztmpl/t.tar.xz")]
        content = _render_containers(provider, containers)
        assert "web_server_01" in content


class TestContainerRootfs:
    """Tests for rootfs/disk rendering."""

    def test_rootfs_rendering(self, provider):
        """Rootfs should render as a disk block."""
        containers = [
            _make_ct(
                ostemplate="s:vztmpl/t.tar.xz",
                rootfs={"storage": "local-lvm", "size": 8},
            )
        ]
        content = _render_containers(provider, containers)
        assert "disk {" in content
        assert 'datastore_id = "local-lvm"' in content
        assert "size         = 8" in content

    def test_rootfs_default_storage(self, provider):
        """Rootfs without explicit storage should use default."""
        containers = [_make_ct(ostemplate="s:vztmpl/t.tar.xz", rootfs={"size": 4})]
        content = _render_containers(provider, containers)
        assert 'datastore_id = "local-lvm"' in content


class TestContainerNetwork:
    """Tests for network interface rendering."""

    def test_single_nic(self, provider):
        """Single NIC should render as network_interface block."""
        containers = [
            _make_ct(
                ostemplate="s:vztmpl/t.tar.xz",
                network=[{"name": "eth0", "bridge": "vmbr0"}],
            )
        ]
        content = _render_containers(provider, containers)
        assert "network_interface {" in content
        assert 'name     = "eth0"' in content
        assert 'bridge   = "vmbr0"' in content

    def test_multi_nic(self, provider):
        """Multiple NICs should produce multiple network_interface blocks."""
        containers = [
            _make_ct(
                ostemplate="s:vztmpl/t.tar.xz",
                network=[
                    {"name": "eth0", "bridge": "vmbr0", "tag": 10},
                    {"name": "eth1", "bridge": "vmbr1", "tag": 20},
                ],
            )
        ]
        content = _render_containers(provider, containers)
        assert content.count("network_interface {") == 2
        assert 'name     = "eth0"' in content
        assert 'name     = "eth1"' in content
        assert "vlan_id  = 10" in content
        assert "vlan_id  = 20" in content

    def test_nic_with_all_options(self, provider):
        """NIC with all options should render all fields."""
        containers = [
            _make_ct(
                ostemplate="s:vztmpl/t.tar.xz",
                network=[
                    {
                        "name": "eth0",
                        "bridge": "vmbr0",
                        "tag": 10,
                        "macaddr": "AA:BB:CC:DD:EE:FF",
                        "firewall": True,
                        "mtu": 1500,
                        "rate_limit": 100,
                    }
                ],
            )
        ]
        content = _render_containers(provider, containers)
        assert 'mac_address = "AA:BB:CC:DD:EE:FF"' in content
        assert "firewall = true" in content
        assert "mtu      = 1500" in content
        assert "rate_limit = 100" in content

    def test_no_network(self, provider):
        """No network should not render network_interface block."""
        containers = [_make_ct(ostemplate="s:vztmpl/t.tar.xz")]
        content = _render_containers(provider, containers)
        assert "network_interface" not in content


class TestContainerMountPoints:
    """Tests for mount point rendering."""

    def test_single_mount_point(self, provider):
        """Single mount point should render correctly."""
        containers = [
            _make_ct(
                ostemplate="s:vztmpl/t.tar.xz",
                mount_point=[{"volume": "nas:data", "path": "/mnt/data"}],
            )
        ]
        content = _render_containers(provider, containers)
        assert "mount_point {" in content
        assert 'volume = "nas:data"' in content
        assert 'path   = "/mnt/data"' in content

    def test_multiple_mount_points(self, provider):
        """Multiple mount points should produce multiple blocks."""
        containers = [
            _make_ct(
                ostemplate="s:vztmpl/t.tar.xz",
                mount_point=[
                    {"volume": "nas:data1", "path": "/mnt/data1"},
                    {
                        "volume": "nas:data2",
                        "path": "/mnt/data2",
                        "shared": True,
                        "read_only": True,
                    },
                ],
            )
        ]
        content = _render_containers(provider, containers)
        assert content.count("mount_point {") == 2
        assert "shared = true" in content
        assert "read_only = true" in content

    def test_mount_point_with_all_options(self, provider):
        """Mount point with all options should render all fields."""
        containers = [
            _make_ct(
                ostemplate="s:vztmpl/t.tar.xz",
                mount_point=[
                    {
                        "volume": "nas:data",
                        "path": "/mnt/data",
                        "size": 10,
                        "acl": True,
                        "backup": False,
                        "quota": True,
                        "read_only": False,
                        "replicate": True,
                        "shared": True,
                    }
                ],
            )
        ]
        content = _render_containers(provider, containers)
        assert '"10G"' in content
        assert "acl    = true" in content
        assert "backup = false" in content
        assert "quota  = true" in content
        assert "replicate = true" in content

    def test_no_mount_points(self, provider):
        """No mount points should not render mount_point block."""
        containers = [_make_ct(ostemplate="s:vztmpl/t.tar.xz")]
        content = _render_containers(provider, containers)
        assert "mount_point" not in content


class TestContainerInitialization:
    """Tests for initialization block rendering."""

    def test_hostname(self, provider):
        """Hostname should render in initialization block."""
        containers = [_make_ct(ostemplate="s:vztmpl/t.tar.xz", hostname="web-01")]
        content = _render_containers(provider, containers)
        assert "initialization {" in content
        assert "hostname {" in content
        assert 'name = "web-01"' in content

    def test_dns(self, provider):
        """DNS should render in initialization block."""
        containers = [
            _make_ct(
                ostemplate="s:vztmpl/t.tar.xz",
                dns={"domain": "example.com", "servers": ["8.8.8.8", "1.1.1.1"]},
            )
        ]
        content = _render_containers(provider, containers)
        assert "dns {" in content
        assert 'domain  = "example.com"' in content
        assert '["8.8.8.8", "1.1.1.1"]' in content

    def test_ip_config_dhcp(self, provider):
        """DHCP IP config should render correctly."""
        containers = [
            _make_ct(
                ostemplate="s:vztmpl/t.tar.xz",
                network=[{"name": "eth0", "bridge": "vmbr0", "ip": "dhcp"}],
            )
        ]
        content = _render_containers(provider, containers)
        assert "ip_config {" in content
        assert 'address = "dhcp"' in content

    def test_ip_config_static(self, provider):
        """Static IP config should render address and gateway."""
        containers = [
            _make_ct(
                ostemplate="s:vztmpl/t.tar.xz",
                network=[
                    {
                        "name": "eth0",
                        "bridge": "vmbr0",
                        "ip": "192.168.10.50/24",
                        "gw": "192.168.10.1",
                    }
                ],
            )
        ]
        content = _render_containers(provider, containers)
        assert 'address = "192.168.10.50/24"' in content
        assert 'gateway = "192.168.10.1"' in content

    def test_ssh_keys(self, provider):
        """SSH keys should render in user_account block."""
        containers = [
            _make_ct(
                ostemplate="s:vztmpl/t.tar.xz",
                ssh_keys=["ssh-rsa AAAA..."],
            )
        ]
        content = _render_containers(provider, containers)
        assert "user_account {" in content
        assert '"ssh-rsa AAAA..."' in content

    def test_password(self, provider):
        """Password should render in user_account block."""
        containers = [_make_ct(ostemplate="s:vztmpl/t.tar.xz", password="secret123")]
        content = _render_containers(provider, containers)
        assert "user_account {" in content
        assert 'password = "secret123"' in content

    def test_no_initialization(self, provider):
        """No initialization fields should not render initialization block."""
        containers = [_make_ct(ostemplate="s:vztmpl/t.tar.xz")]
        content = _render_containers(provider, containers)
        assert "initialization" not in content


class TestContainerFeatures:
    """Tests for features block rendering."""

    def test_nesting(self, provider):
        """Nesting feature should render correctly."""
        containers = [_make_ct(ostemplate="s:vztmpl/t.tar.xz", features={"nesting": True})]
        content = _render_containers(provider, containers)
        assert "features {" in content
        assert "nesting = true" in content

    def test_mount_features(self, provider):
        """Mount features should render as JSON list."""
        containers = [_make_ct(ostemplate="s:vztmpl/t.tar.xz", features={"mount": ["nfs", "cifs"]})]
        content = _render_containers(provider, containers)
        assert '["nfs", "cifs"]' in content

    def test_all_features(self, provider):
        """All features should render correctly."""
        containers = [
            _make_ct(
                ostemplate="s:vztmpl/t.tar.xz",
                features={"nesting": True, "fuse": True, "keyctl": True, "mount": ["nfs"]},
            )
        ]
        content = _render_containers(provider, containers)
        assert "nesting = true" in content
        assert "fuse    = true" in content
        assert "keyctl  = true" in content
        assert '["nfs"]' in content

    def test_no_features(self, provider):
        """No features should not render features block."""
        containers = [_make_ct(ostemplate="s:vztmpl/t.tar.xz")]
        content = _render_containers(provider, containers)
        assert "features" not in content


class TestContainerStartup:
    """Tests for startup block rendering."""

    def test_startup_config(self, provider):
        """Startup configuration should render correctly."""
        containers = [
            _make_ct(
                ostemplate="s:vztmpl/t.tar.xz",
                startup={"order": 1, "up_delay": 10, "down_delay": 5},
            )
        ]
        content = _render_containers(provider, containers)
        assert "startup {" in content
        assert "order      = 1" in content
        assert "up_delay   = 10" in content
        assert "down_delay = 5" in content

    def test_no_startup(self, provider):
        """No startup should not render startup block."""
        containers = [_make_ct(ostemplate="s:vztmpl/t.tar.xz")]
        content = _render_containers(provider, containers)
        assert "startup" not in content


class TestContainerConsole:
    """Tests for console block rendering."""

    def test_console_config(self, provider):
        """Console configuration should render correctly."""
        containers = [
            _make_ct(
                ostemplate="s:vztmpl/t.tar.xz",
                console={"enabled": True, "type": "console", "tty_count": 2},
            )
        ]
        content = _render_containers(provider, containers)
        assert "console {" in content
        assert "enabled   = true" in content
        assert 'type      = "console"' in content
        assert "tty_count = 2" in content

    def test_no_console(self, provider):
        """No console should not render console block."""
        containers = [_make_ct(ostemplate="s:vztmpl/t.tar.xz")]
        content = _render_containers(provider, containers)
        assert "console" not in content


class TestContainerClone:
    """Tests for clone block rendering."""

    def test_clone(self, provider):
        """Clone configuration should render correctly."""
        containers = [
            _make_ct(
                clone={"vm_id": 100, "node_name": "pve02", "datastore_id": "local-lvm"},
            )
        ]
        content = _render_containers(provider, containers)
        assert "clone {" in content
        assert "vm_id = 100" in content
        assert 'node_name    = "pve02"' in content
        assert 'datastore_id = "local-lvm"' in content

    def test_clone_minimal(self, provider):
        """Minimal clone (vm_id only) should render correctly."""
        containers = [_make_ct(clone={"vm_id": 100})]
        content = _render_containers(provider, containers)
        assert "clone {" in content
        assert "vm_id = 100" in content
        assert "node_name" not in content.split("clone {")[1].split("}")[0]


class TestNormalization:
    """Tests for _normalize_container_config()."""

    def test_normalize_dict_network_to_list(self, provider):
        """Single dict network should be wrapped in a list."""
        ct = _make_ct(network={"name": "eth0", "bridge": "vmbr0"})
        result = provider._normalize_container_config(ct)
        assert isinstance(result.config["network"], list)
        assert len(result.config["network"]) == 1
        assert result.config["network"][0]["name"] == "eth0"

    def test_normalize_list_network_unchanged(self, provider):
        """List network should remain a list."""
        nics = [{"name": "eth0", "bridge": "vmbr0"}, {"name": "eth1", "bridge": "vmbr1"}]
        ct = _make_ct(network=nics)
        result = provider._normalize_container_config(ct)
        assert isinstance(result.config["network"], list)
        assert len(result.config["network"]) == 2

    def test_normalize_dict_mount_point_to_list(self, provider):
        """Single dict mount_point should be wrapped in a list."""
        ct = _make_ct(mount_point={"volume": "nas:data", "path": "/mnt/data"})
        result = provider._normalize_container_config(ct)
        assert isinstance(result.config["mount_point"], list)
        assert len(result.config["mount_point"]) == 1
        assert result.config["mount_point"][0]["volume"] == "nas:data"

    def test_normalize_list_mount_point_unchanged(self, provider):
        """List mount_point should remain a list."""
        mps = [
            {"volume": "nas:data1", "path": "/mnt/data1"},
            {"volume": "nas:data2", "path": "/mnt/data2"},
        ]
        ct = _make_ct(mount_point=mps)
        result = provider._normalize_container_config(ct)
        assert isinstance(result.config["mount_point"], list)
        assert len(result.config["mount_point"]) == 2

    def test_normalize_no_network(self, provider):
        """No network key should remain absent."""
        ct = _make_ct(ostemplate="s:vztmpl/t.tar.xz")
        result = provider._normalize_container_config(ct)
        assert "network" not in result.config

    def test_normalize_no_mount_point(self, provider):
        """No mount_point key should remain absent."""
        ct = _make_ct(ostemplate="s:vztmpl/t.tar.xz")
        result = provider._normalize_container_config(ct)
        assert "mount_point" not in result.config

    def test_normalize_does_not_mutate_original(self, provider):
        """Original container config should not be modified."""
        ct = _make_ct(
            network={"name": "eth0", "bridge": "vmbr0"},
            mount_point={"volume": "nas:data", "path": "/mnt"},
        )
        provider._normalize_container_config(ct)
        # Original should still be dicts
        assert isinstance(ct.config["network"], dict)
        assert isinstance(ct.config["mount_point"], dict)


class TestFullContainerRendering:
    """Integration test with a fully-configured container."""

    def test_full_container(self, provider):
        """A container with all fields should render them all correctly."""
        containers = [
            _make_ct(
                name="web-01",
                ctid=300,
                ostemplate="nas01:vztmpl/alpine-3.21.tar.xz",
                ostype="alpine",
                cores=2,
                memory=256,
                swap=128,
                unprivileged=True,
                start=True,
                onboot=True,
                tags=["web", "infra"],
                rootfs={"storage": "nas01", "size": 4},
                network=[
                    {
                        "name": "eth0",
                        "bridge": "vmbr0",
                        "tag": 10,
                        "ip": "192.168.10.50/24",
                        "gw": "192.168.10.1",
                    }
                ],
                mount_point=[{"volume": "nas01:infra", "path": "/var/www/html", "shared": True}],
                hostname="web-01",
                dns={"domain": "example.com", "servers": ["192.168.10.1"]},
                ssh_keys=["ssh-rsa AAAA..."],
                features={"nesting": False, "mount": ["nfs"]},
                startup={"order": 2, "up_delay": 10, "down_delay": 5},
                console={"enabled": True, "type": "console", "tty_count": 2},
            )
        ]
        content = _render_containers(provider, containers)

        # Resource declaration
        assert 'resource "proxmox_virtual_environment_container" "web_01"' in content

        # Top-level attributes
        assert "vm_id       = 300" in content
        assert "unprivileged = true" in content
        assert "started     = true" in content
        assert "start_on_boot = true" in content

        # Operating system
        assert 'template_file_id = "nas01:vztmpl/alpine-3.21.tar.xz"' in content
        assert 'type             = "alpine"' in content

        # CPU & Memory
        assert "cores        = 2" in content
        assert "dedicated = 256" in content
        assert "swap      = 128" in content

        # Disk
        assert 'datastore_id = "nas01"' in content
        assert "size         = 4" in content

        # Network
        assert "network_interface {" in content
        assert 'name     = "eth0"' in content

        # Mount point
        assert "mount_point {" in content
        assert 'volume = "nas01:infra"' in content

        # Initialization
        assert "initialization {" in content
        assert 'name = "web-01"' in content
        assert "dns {" in content
        assert "ip_config {" in content

        # Features
        assert "features {" in content
        assert "nesting = false" in content

        # Startup
        assert "startup {" in content
        assert "order      = 2" in content

        # Console
        assert "console {" in content
        assert "tty_count = 2" in content
