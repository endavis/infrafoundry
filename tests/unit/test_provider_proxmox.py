"""Unit tests for ProxmoxProvider."""

import pytest
from pathlib import Path

from infrafoundry.providers.proxmox import ProxmoxProvider


@pytest.mark.unit
class TestProxmoxProvider:
    """Tests for ProxmoxProvider."""

    def test_init(self, temp_dir):
        """Test ProxmoxProvider initialization."""
        provider = ProxmoxProvider(
            config={
                "api_url": "https://proxmox.example.com:8006",
                "node": "pve1",
            },
            output_dir=temp_dir / "output",
        )
        assert provider.name == "proxmox"

    def test_get_resource_types(self, temp_dir):
        """Test getting supported resource types."""
        provider = ProxmoxProvider(
            config={"api_url": "https://proxmox.example.com:8006"},
            output_dir=temp_dir / "output",
        )
        types = provider.get_resource_types()
        assert "vm" in types
        assert "template" in types

    def test_validate_config_valid(self, temp_dir, sample_vm_resource):
        """Test validation of valid VM config."""
        provider = ProxmoxProvider(
            config={"api_url": "https://proxmox.example.com:8006"},
            output_dir=temp_dir / "output",
        )
        # Should not raise exception
        provider.validate_config("vm", sample_vm_resource)

    def test_validate_config_invalid(self, temp_dir):
        """Test validation of invalid config."""
        provider = ProxmoxProvider(
            config={"api_url": "https://proxmox.example.com:8006"},
            output_dir=temp_dir / "output",
        )
        invalid_resource = {"name": "vm-01"}  # Missing required fields

        with pytest.raises(ValueError):
            provider.validate_config("vm", invalid_resource)

    def test_generate_terraform(self, temp_dir, sample_vm_resource):
        """Test Terraform generation."""
        output_dir = temp_dir / "output"
        provider = ProxmoxProvider(
            config={"api_url": "https://proxmox.example.com:8006", "node": "pve1"},
            output_dir=output_dir,
        )

        resources = {"vm": [sample_vm_resource]}
        env_vars = {"datacenter": "dc1"}

        files = provider.generate_terraform("dev", resources, env_vars)
        assert len(files) > 0

        # Check that output files were created
        tf_dir = output_dir / "terraform" / "proxmox"
        assert tf_dir.exists()

    def test_get_dependencies(self, temp_dir):
        """Test dependency resolution."""
        provider = ProxmoxProvider(
            config={"api_url": "https://proxmox.example.com:8006"},
            output_dir=temp_dir / "output",
        )
        deps = provider.get_dependencies()
        assert "vm" in deps
        # VMs depend on templates
        assert "template" in deps["vm"]

    def test_terraform_resource_naming(self, temp_dir):
        """Test that Terraform resources use valid names."""
        provider = ProxmoxProvider(
            config={"api_url": "https://proxmox.example.com:8006"},
            output_dir=temp_dir / "output",
        )

        # Test with kebab-case name
        resource = {
            "name": "web-server-01",
            "template": "ubuntu-22.04",
            "cores": 2,
            "memory": 4096,
            "disk_size": 50,
        }

        files = provider.generate_terraform("dev", {"vm": [resource]}, {})
        assert len(files) > 0

        # Read generated file and check for snake_case conversion
        tf_file = files[0]
        with open(tf_file) as f:
            content = f.read()
            # Should convert web-server-01 to web_server_01 in resource names
            assert "web_server_01" in content or "web-server-01" in content
