"""Unit tests for ConfigManager."""

import pytest
import yaml

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

        with open(good_env / "settings.yaml", "w") as f:
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

        with open(empty_env / "settings.yaml", "w") as f:
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
        (bad_env / "settings.yaml").write_text("invalid: yaml: content::")

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

    def test_get_resources_with_plural_type(self, temp_dir):
        """Test resource loading with plural type format (e.g., 'vms:' instead of 'vm:')."""
        import yaml

        envs_dir = temp_dir / "envs" / "dev" / "proxmox"
        envs_dir.mkdir(parents=True)

        # Create env config
        env_file = temp_dir / "envs" / "dev" / "settings.yaml"
        env_file.write_text("name: dev\ndescription: Test\n")

        # Create resource file with plural type key (vms instead of vm)
        resource_file = envs_dir / "vm.yaml"
        config_data = {"vms": [{"name": "vm-01", "cores": 4, "memory": 8192}]}  # Plural form
        with open(resource_file, "w") as f:
            yaml.dump(config_data, f)

        config = ConfigManager(temp_dir / "envs")
        resources = config.get_all_resources("dev", "proxmox")
        # Should find resources using plural fallback
        assert len(resources) >= 1
        assert resources[0].name == "vm-01"

    def test_get_resources_with_invalid_type(self, temp_dir):
        """Test resource loading with non-list resource type."""
        import yaml

        envs_dir = temp_dir / "envs" / "dev" / "proxmox"
        envs_dir.mkdir(parents=True)

        # Create env config
        env_file = temp_dir / "envs" / "dev" / "settings.yaml"
        env_file.write_text("name: dev\ndescription: Test\n")

        # Create resource file with dict instead of list
        resource_file = envs_dir / "vm.yaml"
        config_data = {"vm": {"name": "vm-01"}}  # Dict instead of list
        with open(resource_file, "w") as f:
            yaml.dump(config_data, f)

        config = ConfigManager(temp_dir / "envs")
        with pytest.raises(ValueError, match="Expected list"):
            config.get_all_resources("dev", "proxmox")

    def test_get_resources_direct_list_format(self, temp_dir):
        """Test resource loading with direct list format (not dict)."""
        import yaml

        envs_dir = temp_dir / "envs" / "dev" / "proxmox"
        envs_dir.mkdir(parents=True)

        # Create env config
        env_file = temp_dir / "envs" / "dev" / "settings.yaml"
        env_file.write_text("name: dev\ndescription: Test\n")

        # Create resource file as direct list (invalid format)
        resource_file = envs_dir / "vm.yaml"
        config_data = [{"name": "vm-01"}]  # Direct list, not dict
        with open(resource_file, "w") as f:
            yaml.dump(config_data, f)

        config = ConfigManager(temp_dir / "envs")
        resources = config.get_all_resources("dev", "proxmox")
        # Should return empty list for direct list format
        assert len(resources) == 0

    def test_get_resources_from_empty_yaml_file(self, temp_dir):
        """Test get_resources with empty YAML file."""
        envs_dir = temp_dir / "envs" / "dev" / "proxmox"
        envs_dir.mkdir(parents=True, exist_ok=True)

        # Create empty YAML file
        resource_file = envs_dir / "vm.yaml"
        resource_file.write_text("")  # Empty file

        config = ConfigManager(temp_dir / "envs")
        resources = config.get_all_resources("dev", "proxmox")
        # Should return empty list for empty file
        assert len(resources) == 0

    def test_get_all_resources_missing_provider_field(self, temp_dir):
        """Test get_all_resources with missing provider field in resource-centric format."""
        envs_dir = temp_dir / "envs" / "dev" / "resources"
        envs_dir.mkdir(parents=True, exist_ok=True)

        # Create settings.yaml
        env_file = temp_dir / "envs" / "dev" / "settings.yaml"
        env_data = {"name": "dev", "description": "Test"}
        with open(env_file, "w") as f:
            yaml.dump(env_data, f)

        # Create resource file with missing provider field
        resource_file = envs_dir / "test.yaml"
        config_data = {
            "resources": [
                {
                    "type": "vm",  # Missing 'provider' field
                    "name": "web-01",
                    "config": {"cores": 4},
                }
            ]
        }
        with open(resource_file, "w") as f:
            yaml.dump(config_data, f)

        config = ConfigManager(temp_dir / "envs")
        with pytest.raises(ValueError, match="Missing 'provider' field"):
            config.get_all_resources_all_providers("dev")

    def test_get_all_resources_missing_type_field(self, temp_dir):
        """Test get_all_resources with missing type field in resource-centric format."""
        envs_dir = temp_dir / "envs" / "dev" / "resources"
        envs_dir.mkdir(parents=True, exist_ok=True)

        # Create settings.yaml
        env_file = temp_dir / "envs" / "dev" / "settings.yaml"
        env_data = {"name": "dev", "description": "Test"}
        with open(env_file, "w") as f:
            yaml.dump(env_data, f)

        # Create resource file with missing type field
        resource_file = envs_dir / "test.yaml"
        config_data = {
            "resources": [
                {
                    "provider": "proxmox",  # Missing 'type' field
                    "name": "web-01",
                    "config": {"cores": 4},
                }
            ]
        }
        with open(resource_file, "w") as f:
            yaml.dump(config_data, f)

        config = ConfigManager(temp_dir / "envs")
        with pytest.raises(ValueError, match="Missing 'type' field"):
            config.get_all_resources_all_providers("dev")

    def test_get_all_resources_missing_name_field(self, temp_dir):
        """Test get_all_resources with missing name field in resource-centric format."""
        envs_dir = temp_dir / "envs" / "dev" / "resources"
        envs_dir.mkdir(parents=True, exist_ok=True)

        # Create settings.yaml
        env_file = temp_dir / "envs" / "dev" / "settings.yaml"
        env_data = {"name": "dev", "description": "Test"}
        with open(env_file, "w") as f:
            yaml.dump(env_data, f)

        # Create resource file with missing name field
        resource_file = envs_dir / "test.yaml"
        config_data = {
            "resources": [
                {
                    "provider": "proxmox",
                    "type": "vm",  # Missing 'name' field
                    "config": {"cores": 4},
                }
            ]
        }
        with open(resource_file, "w") as f:
            yaml.dump(config_data, f)

        config = ConfigManager(temp_dir / "envs")
        with pytest.raises(ValueError, match="Missing 'name' field"):
            config.get_all_resources_all_providers("dev")

    def test_get_all_resources_duplicate_names(self, temp_dir):
        """Test get_all_resources_all_providers with duplicate resource names."""
        # Create two different files with same resource name
        envs_dir = temp_dir / "envs" / "dev" / "proxmox"
        envs_dir.mkdir(parents=True, exist_ok=True)

        # Create settings.yaml
        env_file = temp_dir / "envs" / "dev" / "settings.yaml"
        env_data = {"name": "dev", "description": "Test"}
        with open(env_file, "w") as f:
            yaml.dump(env_data, f)

        # First file
        file1 = envs_dir / "vm.yaml"
        config1 = {"vm": [{"name": "web-01", "config": {"cores": 2}}]}
        with open(file1, "w") as f:
            yaml.dump(config1, f)

        # Second file with duplicate name
        file2 = envs_dir / "vm-services.yaml"
        config2 = {"vm": [{"name": "web-01", "config": {"cores": 4}}]}
        with open(file2, "w") as f:
            yaml.dump(config2, f)

        config = ConfigManager(temp_dir / "envs")
        with pytest.raises(ValueError, match="Duplicate resource names found"):
            config.get_all_resources_all_providers("dev")

    def test_list_environments_nonexistent_base_dir(self, temp_dir):
        """Test list_environments when base_dir doesn't exist."""
        config = ConfigManager(temp_dir / "nonexistent")
        envs = config.list_environments()
        assert envs == []

    def test_validate_environment_nonexistent(self, temp_dir):
        """Test validate_environment with nonexistent environment."""
        envs_dir = temp_dir / "envs"
        envs_dir.mkdir(parents=True)

        config = ConfigManager(envs_dir)
        assert not config.validate_environment("nonexistent")

    def test_get_resources_skips_settings_yaml_in_provider_dir(self, temp_dir):
        """Test that settings.yaml in provider directory is skipped."""
        envs_dir = temp_dir / "envs" / "dev" / "proxmox"
        envs_dir.mkdir(parents=True, exist_ok=True)

        # Create settings.yaml in provider directory (should be skipped)
        wrong_env_file = envs_dir / "settings.yaml"
        wrong_env_data = {"invalid": "data"}
        with open(wrong_env_file, "w") as f:
            yaml.dump(wrong_env_data, f)

        # Create valid resource file
        vm_file = envs_dir / "vm.yaml"
        vm_data = {"vm": [{"name": "test-vm", "config": {"cores": 2}}]}
        with open(vm_file, "w") as f:
            yaml.dump(vm_data, f)

        config = ConfigManager(temp_dir / "envs")
        resources = config.get_all_resources("dev", "proxmox")
        # Should get only the vm, not fail on settings.yaml
        assert len(resources) == 1
        assert resources[0].name == "test-vm"

    def test_load_resources_with_yaml_returning_none(self, temp_dir):
        """Test load_resources when YAML file contains only comments."""
        envs_dir = temp_dir / "envs" / "dev" / "proxmox"
        envs_dir.mkdir(parents=True, exist_ok=True)

        # Create YAML file with only comments (yaml.safe_load returns None)
        resource_file = envs_dir / "vm.yaml"
        resource_file.write_text("# Just a comment\n# Another comment\n")

        config = ConfigManager(temp_dir / "envs")
        resources = config.get_all_resources("dev", "proxmox")
        # Should return empty list when YAML returns None
        assert len(resources) == 0

    def test_load_resource_centric_files_empty_file(self, temp_dir):
        """Test load_resource_centric_files with empty YAML file."""
        envs_dir = temp_dir / "envs" / "dev" / "resources"
        envs_dir.mkdir(parents=True, exist_ok=True)

        # Create empty YAML file
        resource_file = envs_dir / "test.yaml"
        resource_file.write_text("")

        config = ConfigManager(temp_dir / "envs")
        resources = config.load_resource_centric_files("dev")
        # Should return empty list for empty file
        assert len(resources) == 0

    def test_load_resource_centric_files_missing_resources_key(self, temp_dir):
        """Test load_resource_centric_files when 'resources' key is missing."""
        envs_dir = temp_dir / "envs" / "dev" / "resources"
        envs_dir.mkdir(parents=True, exist_ok=True)

        # Create YAML file without 'resources' key
        resource_file = envs_dir / "test.yaml"
        data = {"other_key": "value"}
        with open(resource_file, "w") as f:
            yaml.dump(data, f)

        config = ConfigManager(temp_dir / "envs")
        resources = config.load_resource_centric_files("dev")
        # Should skip files without 'resources' key
        assert len(resources) == 0

    def test_load_resource_centric_files_non_list_resources(self, temp_dir):
        """Test load_resource_centric_files when resources is not a list."""
        envs_dir = temp_dir / "envs" / "dev" / "resources"
        envs_dir.mkdir(parents=True, exist_ok=True)

        # Create YAML file with resources as dict instead of list
        resource_file = envs_dir / "test.yaml"
        data = {"resources": {"not": "a list"}}
        with open(resource_file, "w") as f:
            yaml.dump(data, f)

        config = ConfigManager(temp_dir / "envs")
        with pytest.raises(ValueError, match="Expected list for 'resources'"):
            config.load_resource_centric_files("dev")

    def test_load_resource_centric_files_non_dict_item(self, temp_dir):
        """Test load_resource_centric_files when resource item is not a dict."""
        envs_dir = temp_dir / "envs" / "dev" / "resources"
        envs_dir.mkdir(parents=True, exist_ok=True)

        # Create YAML file with non-dict item in resources list
        resource_file = envs_dir / "test.yaml"
        data = {
            "resources": [
                "not a dict",  # Invalid item (should be skipped)
                {
                    "provider": "proxmox",
                    "type": "vm",
                    "name": "web-01",
                    "config": {"cores": 2},
                },
            ]
        }
        with open(resource_file, "w") as f:
            yaml.dump(data, f)

        config = ConfigManager(temp_dir / "envs")
        resources = config.load_resource_centric_files("dev")
        # Should skip non-dict items and return only valid resource
        assert len(resources) == 1
        assert resources[0].name == "web-01"

    def test_get_all_resources_all_providers_skips_settings_yaml(self, temp_dir):
        """Test that get_all_resources_all_providers skips settings.yaml."""
        envs_dir = temp_dir / "envs" / "dev" / "proxmox"
        envs_dir.mkdir(parents=True, exist_ok=True)

        # Create settings.yaml in main dir
        env_file = temp_dir / "envs" / "dev" / "settings.yaml"
        env_data = {"name": "dev", "description": "Test"}
        with open(env_file, "w") as f:
            yaml.dump(env_data, f)

        # Create settings.yaml in provider directory (should be skipped)
        wrong_env_file = envs_dir / "settings.yaml"
        wrong_env_data = {"invalid": "data"}
        with open(wrong_env_file, "w") as f:
            yaml.dump(wrong_env_data, f)

        # Create valid resource file
        vm_file = envs_dir / "vm.yaml"
        vm_data = {"vm": [{"name": "test-vm", "config": {"cores": 2}}]}
        with open(vm_file, "w") as f:
            yaml.dump(vm_data, f)

        config = ConfigManager(temp_dir / "envs")
        resources = config.get_all_resources_all_providers("dev")
        # Should get only the vm, not fail on settings.yaml
        assert len(resources) == 1
        assert resources[0].name == "test-vm"

    def test_load_resource_centric_files_missing_provider_direct_call(self, temp_dir):
        """Test load_resource_centric_files directly with missing provider."""
        envs_dir = temp_dir / "envs" / "dev" / "resources"
        envs_dir.mkdir(parents=True, exist_ok=True)

        # Create resource file with missing provider field
        resource_file = envs_dir / "test.yaml"
        config_data = {
            "resources": [
                {
                    "type": "vm",  # Missing 'provider'
                    "name": "web-01",
                    "config": {"cores": 4},
                }
            ]
        }
        with open(resource_file, "w") as f:
            yaml.dump(config_data, f)

        config = ConfigManager(temp_dir / "envs")
        with pytest.raises(ValueError, match="Missing 'provider' field"):
            config.load_resource_centric_files("dev")

    def test_load_resource_centric_files_missing_type_direct_call(self, temp_dir):
        """Test load_resource_centric_files directly with missing type."""
        envs_dir = temp_dir / "envs" / "dev" / "resources"
        envs_dir.mkdir(parents=True, exist_ok=True)

        # Create resource file with missing type field
        resource_file = envs_dir / "test.yaml"
        config_data = {
            "resources": [
                {
                    "provider": "proxmox",  # Missing 'type'
                    "name": "web-01",
                    "config": {"cores": 4},
                }
            ]
        }
        with open(resource_file, "w") as f:
            yaml.dump(config_data, f)

        config = ConfigManager(temp_dir / "envs")
        with pytest.raises(ValueError, match="Missing 'type' field"):
            config.load_resource_centric_files("dev")

    def test_load_resource_centric_files_missing_name_direct_call(self, temp_dir):
        """Test load_resource_centric_files directly with missing name."""
        envs_dir = temp_dir / "envs" / "dev" / "resources"
        envs_dir.mkdir(parents=True, exist_ok=True)

        # Create resource file with missing name field
        resource_file = envs_dir / "test.yaml"
        config_data = {
            "resources": [
                {
                    "provider": "proxmox",
                    "type": "vm",  # Missing 'name'
                    "config": {"cores": 4},
                }
            ]
        }
        with open(resource_file, "w") as f:
            yaml.dump(config_data, f)

        config = ConfigManager(temp_dir / "envs")
        with pytest.raises(ValueError, match="Missing 'name' field"):
            config.load_resource_centric_files("dev")

    def test_load_resources_with_null_yaml(self, temp_dir):
        """Test load_resources when YAML file contains explicit null."""
        envs_dir = temp_dir / "envs" / "dev" / "proxmox"
        envs_dir.mkdir(parents=True, exist_ok=True)

        # Create YAML file with explicit null
        resource_file = envs_dir / "vm.yaml"
        resource_file.write_text("null\n")

        config = ConfigManager(temp_dir / "envs")
        resources = config.get_all_resources("dev", "proxmox")
        # Should return empty list when YAML is null
        assert len(resources) == 0

    def test_load_resources_with_empty_dict(self, temp_dir):
        """Test load_resources when YAML file is empty dict."""
        envs_dir = temp_dir / "envs" / "dev" / "proxmox"
        envs_dir.mkdir(parents=True, exist_ok=True)

        # Create YAML file with empty dict
        resource_file = envs_dir / "vm.yaml"
        resource_file.write_text("{}\n")

        config = ConfigManager(temp_dir / "envs")
        resources = config.get_all_resources("dev", "proxmox")
        # Should return empty list when YAML is empty dict
        assert len(resources) == 0

    def test_get_all_resources_all_providers_with_resources_dir_empty_files(self, temp_dir):
        """Test get_all_resources_all_providers with empty files in resources dir."""
        # Create environment
        envs_dir = temp_dir / "envs" / "dev"
        envs_dir.mkdir(parents=True, exist_ok=True)

        env_file = envs_dir / "settings.yaml"
        env_data = {"name": "dev", "description": "Test"}
        with open(env_file, "w") as f:
            yaml.dump(env_data, f)

        # Create resources directory with empty file
        resources_dir = envs_dir / "resources"
        resources_dir.mkdir(parents=True, exist_ok=True)

        empty_file = resources_dir / "empty.yaml"
        empty_file.write_text("")

        # Create file without resources key
        no_resources = resources_dir / "no_resources.yaml"
        with open(no_resources, "w") as f:
            yaml.dump({"other": "data"}, f)

        config = ConfigManager(temp_dir / "envs")
        resources = config.get_all_resources_all_providers("dev")
        # Should handle empty files and files without resources key
        assert len(resources) == 0

    def test_provider_settings_basic(self, temp_dir):
        """Test provider_settings configuration."""
        envs_dir = temp_dir / "envs" / "test"
        envs_dir.mkdir(parents=True)
        settings_file = envs_dir / "settings.yaml"
        settings_file.write_text(
            """
name: test
description: Test environment
provider_settings:
  proxmox:
    api_url: https://pve01.example.com:8006
    api_token: secret-token
    node: pve01
    storage: local-lvm
  opnsense:
    api_url: https://opn.example.com
    api_key: test-key
"""
        )

        config = ConfigManager(temp_dir / "envs")
        env = config.load_environment("test")

        # Test Proxmox settings
        proxmox_settings = env.get_provider_settings("proxmox")
        assert proxmox_settings is not None
        assert proxmox_settings["api_url"] == "https://pve01.example.com:8006"
        assert proxmox_settings["api_token"] == "secret-token"
        assert proxmox_settings["node"] == "pve01"
        assert proxmox_settings["storage"] == "local-lvm"

        # Test OPNsense settings
        opnsense_settings = env.get_provider_settings("opnsense")
        assert opnsense_settings is not None
        assert opnsense_settings["api_url"] == "https://opn.example.com"
        assert opnsense_settings["api_key"] == "test-key"

        # Test non-existent provider
        k8s_settings = env.get_provider_settings("kubernetes")
        assert k8s_settings is None

    def test_provider_settings_empty(self, temp_dir):
        """Test environment with no provider_settings."""
        envs_dir = temp_dir / "envs" / "test"
        envs_dir.mkdir(parents=True)
        settings_file = envs_dir / "settings.yaml"
        settings_file.write_text(
            """
name: test
description: Test environment
"""
        )

        config = ConfigManager(temp_dir / "envs")
        env = config.load_environment("test")

        # Should return None for any provider
        assert env.get_provider_settings("proxmox") is None
        assert env.get_provider_settings("opnsense") is None

    def test_provider_settings_combined_with_ssh(self, temp_dir):
        """Test provider_settings and provider_ssh together."""
        envs_dir = temp_dir / "envs" / "test"
        envs_dir.mkdir(parents=True)
        settings_file = envs_dir / "settings.yaml"
        settings_file.write_text(
            """
name: test
description: Test environment
ssh:
  user: default-user
provider_ssh:
  proxmox:
    user: proxmox-user
    port: 2222
provider_settings:
  proxmox:
    api_url: https://pve01.example.com:8006
    node: pve01
"""
        )

        config = ConfigManager(temp_dir / "envs")
        env = config.load_environment("test")

        # Test SSH config
        ssh = env.get_ssh_config("proxmox")
        assert ssh is not None
        assert ssh.user == "proxmox-user"
        assert ssh.port == 2222

        # Test provider settings
        settings = env.get_provider_settings("proxmox")
        assert settings is not None
        assert settings["api_url"] == "https://pve01.example.com:8006"
        assert settings["node"] == "pve01"
