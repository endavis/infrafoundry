"""Unit tests for Proxmox inventory template rendering."""

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


class TestInventoryTemplate:
    """Tests for proxmox/inventory.yml.j2 template."""

    def test_ansible_host_override(self, provider):
        """Test ansible_host config override takes priority over ipconfig parsing."""
        custom_host = "custom-ansible-host-override"
        resources = [
            ResourceConfig(
                name="ts-vm",
                type="vms",
                provider="proxmox",
                config={
                    "name": "ts-vm",
                    "ipconfig": "ip=192.168.1.100/24",
                    "ansible_host": custom_host,
                },
            )
        ]
        content = provider.render_template("proxmox/inventory.yml.j2", {"resources": resources})
        assert custom_host in content
        assert "192.168.1.100" not in content

    def test_ansible_host_falls_back_to_ipconfig(self, provider):
        """Test ansible_host falls back to ipconfig when not overridden."""
        resources = [
            ResourceConfig(
                name="regular-vm",
                type="vms",
                provider="proxmox",
                config={
                    "name": "regular-vm",
                    "ipconfig": "ip=10.0.0.50/24",
                },
            )
        ]
        content = provider.render_template("proxmox/inventory.yml.j2", {"resources": resources})
        assert "10.0.0.50" in content

    def test_ansible_host_no_ipconfig_no_override(self, provider):
        """Test CHANGEME fallback when no ansible_host and no ipconfig."""
        resources = [
            ResourceConfig(
                name="bare-vm",
                type="vms",
                provider="proxmox",
                config={
                    "name": "bare-vm",
                },
            )
        ]
        content = provider.render_template("proxmox/inventory.yml.j2", {"resources": resources})
        assert "CHANGEME" in content
