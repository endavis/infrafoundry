"""Unit tests for cloud-init snippet processing in the Proxmox provider.

Tests that all cloud-init directives are passed through to the generated
user-data, not just a hardcoded subset.
"""

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.proxmox import ProxmoxProvider


@pytest.fixture
def provider(tmp_path):
    """Create a ProxmoxProvider with snippet directories."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    # Create snippet directory structure
    snippet_dir = config_dir / "test" / "files" / "cloud-init-snippets"
    snippet_dir.mkdir(parents=True)

    p = ProxmoxProvider(config_dir, output_dir)
    p.set_environment("test")
    return p


@pytest.fixture
def snippet_dir(tmp_path):
    """Return the snippet directory path."""
    return tmp_path / "config" / "test" / "files" / "cloud-init-snippets"


def _make_vm(name: str = "test-vm", **config_overrides) -> ResourceConfig:
    """Helper to create a VM ResourceConfig."""
    config: dict = {
        "name": name,
        "target_node": "pve01",
        **config_overrides,
    }
    return ResourceConfig(name=name, type="vm", provider="proxmox", config=config)


def _write_snippet(snippet_dir, path, content):
    """Write a cloud-init snippet YAML file."""
    full_path = snippet_dir / f"{path}.yaml"
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content)


class TestSnippetPassthrough:
    """Tests that all cloud-init directives are preserved."""

    def test_mounts_preserved(self, provider, snippet_dir):
        """Mounts directive should be included in user-data."""
        _write_snippet(
            snippet_dir,
            "storage/nfs",
            'mounts:\n  - ["10.0.0.1:/export", "/mnt", "nfs", "defaults", "0", "0"]\n',
        )
        vm = _make_vm(cloud_init_snippets=["storage/nfs"])
        result = provider._process_cloud_init_snippets(vm)
        assert "cloud_init_user_data" in result.config
        assert "mounts:" in result.config["cloud_init_user_data"]
        assert "10.0.0.1:/export" in result.config["cloud_init_user_data"]

    def test_write_files_preserved(self, provider, snippet_dir):
        """write_files directive should be included in user-data."""
        _write_snippet(
            snippet_dir,
            "files/config",
            "write_files:\n  - path: /etc/myapp.conf\n    content: key=value\n",
        )
        vm = _make_vm(cloud_init_snippets=["files/config"])
        result = provider._process_cloud_init_snippets(vm)
        assert "write_files:" in result.config["cloud_init_user_data"]
        assert "/etc/myapp.conf" in result.config["cloud_init_user_data"]

    def test_bootcmd_preserved(self, provider, snippet_dir):
        """bootcmd directive should be included in user-data."""
        _write_snippet(
            snippet_dir,
            "boot/early",
            "bootcmd:\n  - echo hello\n",
        )
        vm = _make_vm(cloud_init_snippets=["boot/early"])
        result = provider._process_cloud_init_snippets(vm)
        assert "bootcmd:" in result.config["cloud_init_user_data"]

    def test_swap_preserved(self, provider, snippet_dir):
        """swap directive should be included in user-data."""
        _write_snippet(
            snippet_dir,
            "system/swap",
            "swap:\n  filename: /swapfile\n  size: 1G\n",
        )
        vm = _make_vm(cloud_init_snippets=["system/swap"])
        result = provider._process_cloud_init_snippets(vm)
        assert "swap:" in result.config["cloud_init_user_data"]

    def test_hostname_preserved(self, provider, snippet_dir):
        """hostname directive should be included in user-data."""
        _write_snippet(
            snippet_dir,
            "system/hostname",
            "hostname: web-01\nfqdn: web-01\n",
        )
        vm = _make_vm(cloud_init_snippets=["system/hostname"])
        result = provider._process_cloud_init_snippets(vm)
        user_data = result.config["cloud_init_user_data"]
        assert "hostname: web-01" in user_data
        assert "fqdn: web-01" in user_data

    def test_users_preserved(self, provider, snippet_dir):
        """users directive should be included in user-data."""
        _write_snippet(
            snippet_dir,
            "users/admin",
            "users:\n  - name: admin\n    sudo: ALL=(ALL) NOPASSWD:ALL\n",
        )
        vm = _make_vm(cloud_init_snippets=["users/admin"])
        result = provider._process_cloud_init_snippets(vm)
        assert "users:" in result.config["cloud_init_user_data"]
        assert "admin" in result.config["cloud_init_user_data"]

    def test_packages_preserved(self, provider, snippet_dir):
        """packages directive should be included in user-data."""
        _write_snippet(
            snippet_dir,
            "packages/base",
            "packages:\n  - nginx\n  - curl\n",
        )
        vm = _make_vm(cloud_init_snippets=["packages/base"])
        result = provider._process_cloud_init_snippets(vm)
        assert "packages:" in result.config["cloud_init_user_data"]
        assert "nginx" in result.config["cloud_init_user_data"]

    def test_runcmd_preserved(self, provider, snippet_dir):
        """runcmd directive should be included in user-data."""
        _write_snippet(
            snippet_dir,
            "commands/setup",
            "runcmd:\n  - systemctl enable nginx\n",
        )
        vm = _make_vm(cloud_init_snippets=["commands/setup"])
        result = provider._process_cloud_init_snippets(vm)
        assert "runcmd:" in result.config["cloud_init_user_data"]

    def test_network_preserved(self, provider, snippet_dir):
        """network directive should be included in user-data."""
        _write_snippet(
            snippet_dir,
            "network/dhcp",
            "network:\n  version: 2\n  ethernets:\n    eth0:\n      dhcp4: true\n",
        )
        vm = _make_vm(cloud_init_snippets=["network/dhcp"])
        result = provider._process_cloud_init_snippets(vm)
        assert "network:" in result.config["cloud_init_user_data"]
        assert "dhcp4: true" in result.config["cloud_init_user_data"]


class TestSnippetMerging:
    """Tests for merging multiple snippets."""

    def test_multiple_snippets_merged(self, provider, snippet_dir):
        """Multiple snippets should be deep-merged."""
        _write_snippet(snippet_dir, "users/admin", "users:\n  - name: admin\n")
        _write_snippet(snippet_dir, "packages/base", "packages:\n  - nginx\n")
        _write_snippet(
            snippet_dir,
            "storage/nfs",
            'mounts:\n  - ["10.0.0.1:/data", "/mnt", "nfs"]\n',
        )
        vm = _make_vm(cloud_init_snippets=["users/admin", "packages/base", "storage/nfs"])
        result = provider._process_cloud_init_snippets(vm)
        user_data = result.config["cloud_init_user_data"]
        assert "users:" in user_data
        assert "packages:" in user_data
        assert "mounts:" in user_data

    def test_list_fields_merged(self, provider, snippet_dir):
        """List fields from multiple snippets should be concatenated."""
        _write_snippet(snippet_dir, "packages/a", "packages:\n  - nginx\n")
        _write_snippet(snippet_dir, "packages/b", "packages:\n  - curl\n")
        vm = _make_vm(cloud_init_snippets=["packages/a", "packages/b"])
        result = provider._process_cloud_init_snippets(vm)
        user_data = result.config["cloud_init_user_data"]
        assert "nginx" in user_data
        assert "curl" in user_data

    def test_variable_substitution(self, provider, snippet_dir):
        """Variables in snippets should be substituted."""
        _write_snippet(
            snippet_dir,
            "system/hostname",
            "hostname: ${HOSTNAME}\n",
        )
        vm = _make_vm(
            cloud_init_snippets=["system/hostname"],
            cloud_init_vars={"HOSTNAME": "web-01"},
        )
        result = provider._process_cloud_init_snippets(vm)
        assert "hostname: web-01" in result.config["cloud_init_user_data"]


class TestSnippetEdgeCases:
    """Edge cases for snippet processing."""

    def test_no_snippets_no_user_data(self, provider):
        """VM without snippets should not have cloud_init_user_data."""
        vm = _make_vm()
        result = provider._process_cloud_init_snippets(vm)
        assert "cloud_init_user_data" not in result.config

    def test_missing_snippet_warns(self, provider, caplog):
        """Missing snippet should log a warning (not raise)."""
        import logging

        vm = _make_vm(cloud_init_snippets=["nonexistent/snippet"])
        provider.fail_on_missing_snippets = False
        with caplog.at_level(logging.WARNING):
            result = provider._process_cloud_init_snippets(vm)
        assert "Cloud-init snippet not found" in caplog.text
        assert "cloud_init_user_data" not in result.config

    def test_missing_snippet_strict_raises(self, provider):
        """Missing snippet in strict mode should raise FileNotFoundError."""
        vm = _make_vm(cloud_init_snippets=["nonexistent/snippet"])
        provider.fail_on_missing_snippets = True
        with pytest.raises(FileNotFoundError):
            provider._process_cloud_init_snippets(vm)

    def test_does_not_mutate_original(self, provider, snippet_dir):
        """Original VM config should not be modified."""
        _write_snippet(snippet_dir, "packages/base", "packages:\n  - nginx\n")
        vm = _make_vm(cloud_init_snippets=["packages/base"])
        provider._process_cloud_init_snippets(vm)
        assert "cloud_init_user_data" not in vm.config


class TestTemplateRendering:
    """Tests that the template renders cloud-init user-data correctly."""

    def test_user_data_creates_file_resource(self, provider, snippet_dir):
        """VM with snippets should create a proxmox_virtual_environment_file resource."""
        _write_snippet(snippet_dir, "packages/base", "packages:\n  - nginx\n")
        vm = _make_vm(
            cloud_init_snippets=["packages/base"],
            cloud_init_snippets_storage="nas01",
            ipconfig="ip=dhcp",
        )
        processed = provider._process_cloud_init_snippets(vm)
        processed = provider._normalize_vm_config(processed)
        content = provider.render_template("proxmox/vms.tf.j2", {"vms": [processed]})
        assert "proxmox_virtual_environment_file" in content
        assert "#cloud-config" in content
        assert "nginx" in content
        assert "user_data_file_id" in content

    def test_no_snippets_no_file_resource(self, provider):
        """VM without snippets should not create a file resource."""
        vm = _make_vm(ipconfig="ip=dhcp")
        processed = provider._normalize_vm_config(vm)
        content = provider.render_template("proxmox/vms.tf.j2", {"vms": [processed]})
        assert "proxmox_virtual_environment_file" not in content

    def test_mounts_in_rendered_output(self, provider, snippet_dir):
        """Mounts should appear in the rendered Terraform output."""
        _write_snippet(
            snippet_dir,
            "storage/nfs",
            'mounts:\n  - ["10.0.0.1:/export", "/mnt", "nfs"]\n',
        )
        vm = _make_vm(
            cloud_init_snippets=["storage/nfs"],
            ipconfig="ip=dhcp",
        )
        processed = provider._process_cloud_init_snippets(vm)
        processed = provider._normalize_vm_config(processed)
        content = provider.render_template("proxmox/vms.tf.j2", {"vms": [processed]})
        assert "mounts:" in content
        assert "10.0.0.1:/export" in content

    def test_ip_config_alongside_user_data(self, provider, snippet_dir):
        """ipconfig should render ip_config block alongside custom user-data."""
        _write_snippet(snippet_dir, "users/admin", "users:\n  - name: admin\n")
        vm = _make_vm(
            cloud_init_snippets=["users/admin"],
            ipconfig="ip=dhcp",
        )
        processed = provider._process_cloud_init_snippets(vm)
        processed = provider._normalize_vm_config(processed)
        content = provider.render_template("proxmox/vms.tf.j2", {"vms": [processed]})
        assert "ip_config {" in content
        assert 'address = "dhcp"' in content
