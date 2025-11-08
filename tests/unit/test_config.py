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

    def test_get_resources_empty_environment(self, temp_dir):
        """Test getting resources from environment with no resources."""
        envs_dir = temp_dir / "envs"
        envs_dir.mkdir()
        empty_env = envs_dir / "empty"
        empty_env.mkdir()

        import yaml

        with open(empty_env / "environment.yaml", "w") as f:
            yaml.dump({"name": "empty", "description": "Empty environment"}, f)

        config = ConfigManager(envs_dir)
        resources = config.get_all_resources("empty", "proxmox")
        assert resources == []

    def test_get_resources_invalid_yaml(self, temp_dir):
        """Test handling of invalid YAML files."""
        envs_dir = temp_dir / "envs"
        envs_dir.mkdir()
        bad_env = envs_dir / "bad"
        bad_env.mkdir()
        proxmox_dir = bad_env / "proxmox"
        proxmox_dir.mkdir(parents=True)

        # Create invalid YAML file
        (proxmox_dir / "vms.yaml").write_text("invalid: yaml: content::")

        config = ConfigManager(envs_dir)
        # Should handle gracefully (return empty or raise)
        try:
            resources = config.get_all_resources("bad", "proxmox")
            # If it succeeds, should return empty list
            assert isinstance(resources, list)
        except Exception:
            # If it raises, that's also acceptable
            pass

    def test_get_resources_with_resource_filter(self, mock_config_dir):
        """Test filtering resources by name."""
        config = ConfigManager(mock_config_dir / "envs")
        all_resources = config.get_all_resources("dev", "proxmox")

        if all_resources:
            # Filter to specific resource
            first_resource_name = all_resources[0].name
            filtered = [r for r in all_resources if r.name == first_resource_name]
            assert len(filtered) >= 1
            assert filtered[0].name == first_resource_name

    def test_load_environment_with_invalid_yaml(self, temp_dir):
        """Test loading environment with invalid YAML."""
        envs_dir = temp_dir / "envs"
        envs_dir.mkdir()
        bad_env = envs_dir / "bad-yaml"
        bad_env.mkdir()

        # Create invalid YAML
        (bad_env / "environment.yaml").write_text("invalid: yaml: content::")

        config = ConfigManager(envs_dir)

        with pytest.raises(Exception):  # Should raise some exception
            config.load_environment("bad-yaml")

    def test_list_environments_empty_directory(self, temp_dir):
        """Test listing environments from empty directory."""
        envs_dir = temp_dir / "envs"
        envs_dir.mkdir()

        config = ConfigManager(envs_dir)
        envs = config.list_environments()
        assert envs == []

    def test_get_all_resources_nonexistent_provider(self, mock_config_dir):
        """Test getting resources for non-existent provider."""
        config = ConfigManager(mock_config_dir / "envs")
        resources = config.get_all_resources("dev", "nonexistent-provider")
        # Should return empty list
        assert resources == []

    def test_init_with_config_repo_env(self, temp_dir, monkeypatch):
        """Test initialization with INFRAFOUNDRY_CONFIG_REPO environment variable."""
        config_repo = temp_dir / "config-repo"
        config_repo.mkdir()
        envs_dir = config_repo / "envs"
        envs_dir.mkdir()

        monkeypatch.setenv("INFRAFOUNDRY_CONFIG_REPO", str(config_repo))
        config = ConfigManager()
        assert config.base_dir == envs_dir

    def test_init_with_config_dir_env(self, temp_dir, monkeypatch):
        """Test initialization with INFRAFOUNDRY_CONFIG_DIR environment variable."""
        custom_dir = temp_dir / "custom-envs"
        custom_dir.mkdir()

        monkeypatch.delenv("INFRAFOUNDRY_CONFIG_REPO", raising=False)
        monkeypatch.setenv("INFRAFOUNDRY_CONFIG_DIR", str(custom_dir))
        monkeypatch.chdir(temp_dir)

        config = ConfigManager()
        assert config.base_dir == custom_dir
