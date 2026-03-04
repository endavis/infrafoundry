"""Unit tests for Proxmox storage resource type support.

Tests template rendering, resource type registration, and dependency resolution
for NFS, CIFS, and directory storage backends.
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


def _make_storage(name: str = "test-storage", **config_overrides) -> ResourceConfig:
    """Helper to create a storage ResourceConfig with sensible defaults."""
    config: dict = {
        "name": name,
        **config_overrides,
    }
    return ResourceConfig(name=name, type="storage", provider="proxmox", config=config)


def _render_storage(provider: ProxmoxProvider, storages: list[ResourceConfig]) -> str:
    """Render storage resources through the template."""
    return provider.render_template("proxmox/storage.tf.j2", {"storages": storages})


class TestResourceRegistration:
    """Tests for storage resource type registration."""

    def test_resource_types_include_storage(self, provider):
        """Storage should be in the list of supported resource types."""
        types = provider.get_resource_types()
        assert "storage" in types

    def test_dependencies_include_storage(self, provider):
        """Storage should have no dependencies."""
        deps = provider.get_dependencies()
        assert "storage" in deps
        assert deps["storage"] == []

    def test_vm_depends_on_storage(self, provider):
        """VM dependencies should include storage."""
        deps = provider.get_dependencies()
        assert "storage" in deps["vm"]

    def test_container_depends_on_storage(self, provider):
        """Container dependencies should include storage."""
        deps = provider.get_dependencies()
        assert "storage" in deps["container"]

    def test_existing_types_still_present(self, provider):
        """Existing resource types should still be registered."""
        types = provider.get_resource_types()
        assert "vm" in types
        assert "container" in types
        assert "template" in types
        assert "network" in types


class TestNFSRendering:
    """Tests for NFS storage template rendering."""

    def test_basic_nfs(self, provider):
        """Basic NFS storage should render the correct Terraform resource."""
        storages = [
            _make_storage(
                name="nas01-infra",
                backend="nfs",
                server="192.168.10.50",
                export="/export/infra",
            )
        ]
        content = _render_storage(provider, storages)
        assert 'resource "proxmox_virtual_environment_storage_nfs"' in content
        assert '"nas01_infra"' in content
        assert 'id     = "nas01-infra"' in content
        assert 'server = "192.168.10.50"' in content
        assert 'export = "/export/infra"' in content

    def test_nfs_with_content_types(self, provider):
        """NFS with content_types should render the content attribute."""
        storages = [
            _make_storage(
                backend="nfs",
                server="192.168.10.50",
                export="/export/infra",
                content_types=["snippets", "vztmpl", "iso"],
            )
        ]
        content = _render_storage(provider, storages)
        assert "content" in content
        assert '"snippets"' in content
        assert '"vztmpl"' in content
        assert '"iso"' in content

    def test_nfs_with_nodes(self, provider):
        """NFS with nodes should render the nodes attribute."""
        storages = [
            _make_storage(
                backend="nfs",
                server="192.168.10.50",
                export="/export/infra",
                nodes=["pve1", "pve2", "pve3"],
            )
        ]
        content = _render_storage(provider, storages)
        assert "nodes" in content
        assert '"pve1"' in content
        assert '"pve2"' in content

    def test_nfs_with_all_options(self, provider):
        """NFS with all optional fields should render them."""
        storages = [
            _make_storage(
                backend="nfs",
                server="192.168.10.50",
                export="/export/infra",
                content_types=["snippets"],
                nodes=["pve1"],
                disable=True,
                preallocation="full",
            )
        ]
        content = _render_storage(provider, storages)
        assert "disable = true" in content
        assert 'preallocation = "full"' in content


class TestCIFSRendering:
    """Tests for CIFS storage template rendering."""

    def test_basic_cifs(self, provider):
        """Basic CIFS storage should render the correct Terraform resource."""
        storages = [
            _make_storage(
                name="backup-share",
                backend="cifs",
                server="192.168.10.50",
                share="backups",
            )
        ]
        content = _render_storage(provider, storages)
        assert 'resource "proxmox_virtual_environment_storage_cifs"' in content
        assert '"backup_share"' in content
        assert 'id     = "backup-share"' in content
        assert 'server = "192.168.10.50"' in content
        assert 'share  = "backups"' in content

    def test_cifs_with_credentials(self, provider):
        """CIFS with username/password should render credential attributes."""
        storages = [
            _make_storage(
                backend="cifs",
                server="192.168.10.50",
                share="backups",
                username="proxmox",
                password="secret",
            )
        ]
        content = _render_storage(provider, storages)
        assert 'username = "proxmox"' in content
        assert 'password = "secret"' in content

    def test_cifs_with_domain_and_subdirectory(self, provider):
        """CIFS with domain and subdirectory should render them."""
        storages = [
            _make_storage(
                backend="cifs",
                server="192.168.10.50",
                share="backups",
                domain="WORKGROUP",
                subdirectory="proxmox-backups",
            )
        ]
        content = _render_storage(provider, storages)
        assert 'domain = "WORKGROUP"' in content
        assert 'subdir = "proxmox-backups"' in content


class TestDirRendering:
    """Tests for directory storage template rendering."""

    def test_basic_dir(self, provider):
        """Basic dir storage should render the correct Terraform resource."""
        storages = [
            _make_storage(
                name="local-snippets",
                backend="dir",
                path="/mnt/snippets",
            )
        ]
        content = _render_storage(provider, storages)
        assert 'resource "proxmox_virtual_environment_storage_dir"' in content
        assert '"local_snippets"' in content
        assert 'id     = "local-snippets"' in content
        assert 'path   = "/mnt/snippets"' in content

    def test_dir_with_shared(self, provider):
        """Dir with shared flag should render the shared attribute."""
        storages = [
            _make_storage(
                backend="dir",
                path="/mnt/snippets",
                shared=False,
            )
        ]
        content = _render_storage(provider, storages)
        assert "shared = false" in content


class TestCommonOptions:
    """Tests for common storage options across backends."""

    def test_disable_option(self, provider):
        """Disable option should work for all backends."""
        for backend, extra in [
            ("nfs", {"server": "1.2.3.4", "export": "/e"}),
            ("cifs", {"server": "1.2.3.4", "share": "s"}),
            ("dir", {"path": "/mnt"}),
        ]:
            storages = [_make_storage(backend=backend, disable=True, **extra)]
            content = _render_storage(provider, storages)
            assert "disable = true" in content

    def test_content_types_across_backends(self, provider):
        """content_types should render for all backends."""
        for backend, extra in [
            ("nfs", {"server": "1.2.3.4", "export": "/e"}),
            ("cifs", {"server": "1.2.3.4", "share": "s"}),
            ("dir", {"path": "/mnt"}),
        ]:
            storages = [_make_storage(backend=backend, content_types=["backup"], **extra)]
            content = _render_storage(provider, storages)
            assert '"backup"' in content

    def test_nodes_across_backends(self, provider):
        """nodes should render for all backends."""
        for backend, extra in [
            ("nfs", {"server": "1.2.3.4", "export": "/e"}),
            ("cifs", {"server": "1.2.3.4", "share": "s"}),
            ("dir", {"path": "/mnt"}),
        ]:
            storages = [_make_storage(backend=backend, nodes=["pve1"], **extra)]
            content = _render_storage(provider, storages)
            assert '"pve1"' in content


class TestNameNormalization:
    """Tests for name normalization (dashes to underscores)."""

    def test_dashes_replaced_in_resource_name(self, provider):
        """Dashes in storage name should be replaced with underscores in resource ID."""
        storages = [
            _make_storage(
                name="my-nfs-storage",
                backend="nfs",
                server="1.2.3.4",
                export="/e",
            )
        ]
        content = _render_storage(provider, storages)
        assert '"my_nfs_storage"' in content
        # But the Proxmox ID should keep dashes
        assert 'id     = "my-nfs-storage"' in content


class TestIntegration:
    """Integration test with multiple storage backends."""

    def test_multiple_backends(self, provider):
        """Multiple storage backends should all render in the same file."""
        storages = [
            _make_storage(
                name="nfs-store",
                backend="nfs",
                server="192.168.1.1",
                export="/export/data",
            ),
            _make_storage(
                name="cifs-store",
                backend="cifs",
                server="192.168.1.2",
                share="share",
                username="admin",
            ),
            _make_storage(
                name="dir-store",
                backend="dir",
                path="/mnt/local",
            ),
        ]
        content = _render_storage(provider, storages)
        assert 'resource "proxmox_virtual_environment_storage_nfs"' in content
        assert 'resource "proxmox_virtual_environment_storage_cifs"' in content
        assert 'resource "proxmox_virtual_environment_storage_dir"' in content
        assert '"nfs_store"' in content
        assert '"cifs_store"' in content
        assert '"dir_store"' in content
