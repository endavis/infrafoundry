"""Unit tests for ConfigManager."""

import pytest
import yaml

from infrafoundry.core.config import ConfigManager


@pytest.mark.unit
class TestConfigManager:
    """Tests for ConfigManager."""

    def test_init(self, mock_config_dir):
        """Test ConfigManager initialization."""
        config = ConfigManager(str(mock_config_dir / "envs"))
        assert config.config_dir.name == "envs"

    def test_list_environments(self, mock_config_dir):
        """Test listing environments."""
        config = ConfigManager(str(mock_config_dir / "envs"))
        envs = config.list_environments()
        assert "dev" in envs
        assert len(envs) == 1

    def test_get_environment(self, mock_config_dir):
        """Test getting environment configuration."""
        config = ConfigManager(str(mock_config_dir / "envs"))
        env = config.get_environment("dev")
        assert env["name"] == "dev"
        assert env["description"] == "Development environment"
        assert "datacenter" in env["variables"]

    def test_get_environment_not_found(self, mock_config_dir):
        """Test getting non-existent environment."""
        config = ConfigManager(str(mock_config_dir / "envs"))
        with pytest.raises(FileNotFoundError):
            config.get_environment("nonexistent")

    def test_get_provider_resources_provider_centric(self, mock_config_dir):
        """Test getting resources from provider-centric structure."""
        config = ConfigManager(str(mock_config_dir / "envs"))
        resources = config.get_provider_resources("dev", "proxmox")
        assert "vm" in resources
        assert len(resources["vm"]) == 1
        assert resources["vm"][0]["name"] == "test-vm-01"

    def test_get_provider_resources_resource_centric(self, mock_config_dir):
        """Test getting resources from resource-centric structure."""
        config = ConfigManager(str(mock_config_dir / "envs"))
        resources = config.get_provider_resources("dev", "proxmox")
        # Should include both provider-centric and resource-centric resources
        assert "vm" in resources
        # Should have resources from both formats
        vm_names = {vm["name"] for vm in resources["vm"]}
        assert "test-vm-01" in vm_names
        assert "web-server-01" in vm_names

    def test_get_all_resources_all_providers(self, mock_config_dir):
        """Test getting all resources across all providers."""
        config = ConfigManager(str(mock_config_dir / "envs"))
        all_resources = config.get_all_resources_all_providers("dev")
        assert "proxmox" in all_resources
        assert "vm" in all_resources["proxmox"]

    def test_validate_environment_structure(self, temp_dir):
        """Test validation of environment directory structure."""
        # Create incomplete environment
        envs_dir = temp_dir / "envs"
        envs_dir.mkdir()
        broken_env = envs_dir / "broken"
        broken_env.mkdir()

        config = ConfigManager(str(envs_dir))
        envs = config.list_environments()
        # Should not include broken environment without environment.yaml
        assert "broken" not in envs
