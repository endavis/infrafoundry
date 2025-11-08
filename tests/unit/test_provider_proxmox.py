"""Unit tests for ProxmoxProvider."""

import pytest

from infrafoundry.providers.proxmox import ProxmoxProvider


@pytest.mark.unit
class TestProxmoxProvider:
    """Tests for ProxmoxProvider."""

    def test_init(self, temp_dir):
        """Test ProxmoxProvider initialization."""
        config_dir = temp_dir / "config"
        config_dir.mkdir()
        output_dir = temp_dir / "output"
        
        provider = ProxmoxProvider(
            config_dir=config_dir,
            output_dir=output_dir,
        )
        assert provider.name == "proxmox"

    def test_get_resource_types(self, temp_dir):
        """Test getting supported resource types."""
        config_dir = temp_dir / "config"
        config_dir.mkdir()
        
        provider = ProxmoxProvider(
            config_dir=config_dir,
            output_dir=temp_dir / "output",
        )
        types = provider.get_resource_types()
        assert "vm" in types
        assert "template" in types

    def test_get_dependencies(self, temp_dir):
        """Test dependency resolution."""
        config_dir = temp_dir / "config"
        config_dir.mkdir()
        
        provider = ProxmoxProvider(
            config_dir=config_dir,
            output_dir=temp_dir / "output",
        )
        deps = provider.get_dependencies()
        assert "vm" in deps
        # VMs depend on templates
        assert "template" in deps["vm"]
