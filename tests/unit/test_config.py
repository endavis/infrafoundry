"""Unit tests for ConfigManager."""

import pytest

from infrafoundry.core.config import ConfigManager


@pytest.mark.unit
class TestConfigManager:
    """Tests for ConfigManager."""

    def test_init(self, mock_config_dir):
        """Test ConfigManager initialization."""
        config = ConfigManager(mock_config_dir / "envs")
        assert config.base_dir.name == "envs"

    def test_list_environments(self, mock_config_dir):
        """Test listing environments."""
        config = ConfigManager(mock_config_dir / "envs")
        envs = config.list_environments()
        assert "dev" in envs
        assert len(envs) == 1

    def test_load_environment(self, mock_config_dir):
        """Test loading environment configuration."""
        config = ConfigManager(mock_config_dir / "envs")
        env = config.load_environment("dev")
        assert env.name == "dev"
        assert env.description == "Development environment"
        assert "datacenter" in env.variables

    def test_load_environment_not_found(self, mock_config_dir):
        """Test loading non-existent environment."""
        config = ConfigManager(mock_config_dir / "envs")
        with pytest.raises(FileNotFoundError):
            config.load_environment("nonexistent")

    def test_get_all_resources(self, mock_config_dir):
        """Test getting resources for a provider."""
        config = ConfigManager(mock_config_dir / "envs")
        resources = config.get_all_resources("dev", "proxmox")
        # Should have resources from both provider-centric and resource-centric
        assert len(resources) >= 1
        # Check that we got VM resources
        vm_resources = [r for r in resources if r.type == "vm"]
        assert len(vm_resources) >= 1

    def test_get_all_resources_all_providers(self, mock_config_dir):
        """Test getting all resources across all providers."""
        config = ConfigManager(mock_config_dir / "envs")
        all_resources = config.get_all_resources_all_providers("dev")
        assert len(all_resources) > 0
        # Should have proxmox resources
        proxmox_resources = [r for r in all_resources if r.provider == "proxmox"]
        assert len(proxmox_resources) > 0

    def test_validate_environment_structure(self, temp_dir):
        """Test validation of environment directory structure."""
        # Create incomplete environment
        envs_dir = temp_dir / "envs"
        envs_dir.mkdir()
        broken_env = envs_dir / "broken"
        broken_env.mkdir()

        config = ConfigManager(envs_dir)
        
        # List will include broken, but validate will fail
        envs = config.list_environments()
        assert "broken" in envs
        
        # Validate should return False for incomplete environment
        assert not config.validate_environment("broken")
        
        # Create complete environment
        good_env = envs_dir / "good"
        good_env.mkdir()
        import yaml
        with open(good_env / "environment.yaml", "w") as f:
            yaml.dump({"name": "good", "description": "Good env"}, f)
        
        # Now validate should pass
        assert config.validate_environment("good")
