"""Unit tests for config create and show CLI commands."""

from __future__ import annotations

import pytest
import yaml
from click.testing import CliRunner

from infrafoundry.cli.main import main


@pytest.fixture
def cli_runner():
    """Fixture for invoking CLI commands."""
    return CliRunner()


@pytest.fixture
def temp_config_dir(tmp_path):
    """Create a temporary config directory with sample environment."""
    config_dir = tmp_path / "config"
    envs_dir = config_dir / "envs"

    # Create dev environment
    dev_dir = envs_dir / "dev"
    dev_dir.mkdir(parents=True)

    settings = {
        "name": "dev",
        "description": "Development environment",
        "providers": ["proxmox", "kubernetes"],
    }
    with open(dev_dir / "settings.yaml", "w") as f:
        yaml.safe_dump(settings, f)

    # Create a sample resource file
    resources_dir = dev_dir / "resources"
    resources_dir.mkdir()
    resource_config = {
        "resources": [
            {
                "name": "test-vm",
                "provider": "proxmox",
                "type": "vm",
                "config": {"cpu": 2, "memory": 4096},
            }
        ]
    }
    with open(resources_dir / "vms.yaml", "w") as f:
        yaml.safe_dump(resource_config, f)

    return config_dir


class TestConfigCreate:
    """Tests for config create command."""

    def test_create_creates_minimal_environment(self, cli_runner, tmp_path):
        """Test create creates minimal environment structure."""
        config_dir = tmp_path / "config"
        envs_dir = config_dir / "envs"
        envs_dir.mkdir(parents=True)

        result = cli_runner.invoke(
            main,
            ["--config-dir", str(config_dir), "config", "create", "staging"],
        )

        assert result.exit_code == 0
        assert "Environment 'staging' created" in result.output

        # Verify directory structure
        staging_dir = envs_dir / "staging"
        assert staging_dir.exists()
        assert (staging_dir / "settings.yaml").exists()
        assert (staging_dir / "resources").exists()

        # Verify settings content
        with open(staging_dir / "settings.yaml") as f:
            settings = yaml.safe_load(f)
        assert settings["name"] == "staging"

    def test_create_with_description(self, cli_runner, tmp_path):
        """Test create with custom description."""
        config_dir = tmp_path / "config"
        envs_dir = config_dir / "envs"
        envs_dir.mkdir(parents=True)

        result = cli_runner.invoke(
            main,
            [
                "--config-dir",
                str(config_dir),
                "config",
                "create",
                "prod",
                "-d",
                "Production environment",
            ],
        )

        assert result.exit_code == 0

        with open(envs_dir / "prod" / "settings.yaml") as f:
            settings = yaml.safe_load(f)
        assert settings["description"] == "Production environment"

    def test_create_from_existing_environment(self, cli_runner, temp_config_dir):
        """Test create --from scaffolds from existing environment."""
        result = cli_runner.invoke(
            main,
            [
                "--config-dir",
                str(temp_config_dir),
                "config",
                "create",
                "staging",
                "--from",
                "dev",
            ],
        )

        assert result.exit_code == 0
        assert "Environment 'staging' created from 'dev'" in result.output

        # Verify the new environment has copied structure
        staging_dir = temp_config_dir / "envs" / "staging"
        assert staging_dir.exists()
        assert (staging_dir / "settings.yaml").exists()
        assert (staging_dir / "resources").exists()
        assert (staging_dir / "resources" / "vms.yaml").exists()

        # Verify settings were updated
        with open(staging_dir / "settings.yaml") as f:
            settings = yaml.safe_load(f)
        assert settings["name"] == "staging"

    def test_create_from_nonexistent_environment(self, cli_runner, temp_config_dir):
        """Test create --from with nonexistent source fails."""
        result = cli_runner.invoke(
            main,
            [
                "--config-dir",
                str(temp_config_dir),
                "config",
                "create",
                "staging",
                "--from",
                "nonexistent",
            ],
        )

        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_create_existing_environment_fails_without_force(self, cli_runner, temp_config_dir):
        """Test create fails if environment exists without --force."""
        result = cli_runner.invoke(
            main,
            ["--config-dir", str(temp_config_dir), "config", "create", "dev"],
        )

        assert result.exit_code != 0
        assert "already exists" in result.output

    def test_create_existing_environment_with_force(self, cli_runner, temp_config_dir):
        """Test create --force overwrites existing environment."""
        result = cli_runner.invoke(
            main,
            [
                "--config-dir",
                str(temp_config_dir),
                "config",
                "create",
                "dev",
                "--force",
                "-d",
                "Recreated dev",
            ],
        )

        assert result.exit_code == 0
        assert "Environment 'dev' created" in result.output

        with open(temp_config_dir / "envs" / "dev" / "settings.yaml") as f:
            settings = yaml.safe_load(f)
        assert settings["description"] == "Recreated dev"

    def test_create_without_config_dir(self, cli_runner, monkeypatch):
        """Test create fails without config directory."""
        # Clear the env var to ensure no config dir is set
        monkeypatch.delenv("INFRAFOUNDRY_CONFIG_REPO", raising=False)

        with cli_runner.isolated_filesystem():
            result = cli_runner.invoke(main, ["config", "create", "test-env-no-config"])

            # Should fail because no config dir is set
            assert result.exit_code != 0
            assert "Config directory not set" in result.output or "config" in result.output.lower()

    def test_create_from_sops_encrypted_settings(self, cli_runner, tmp_path):
        """Test create --from handles SOPS-encrypted settings.yaml."""
        config_dir = tmp_path / "config"
        envs_dir = config_dir / "envs"

        # Create source environment with SOPS-encrypted settings
        dev_dir = envs_dir / "dev"
        dev_dir.mkdir(parents=True)

        sops_content = (
            "name: ENC[AES256_GCM,data:abc123]\n"
            "description: ENC[AES256_GCM,data:dev-desc]\n"
            "providers:\n"
            "- proxmox\n"
            "sops:\n"
            "    version: 3.7.3\n"
        )
        (dev_dir / "settings.yaml").write_text(sops_content)

        decrypted_yaml = "name: dev\ndescription: Development environment\nproviders:\n- proxmox\n"
        mock_decrypt = type("Result", (), {"stdout": decrypted_yaml, "returncode": 0})()
        mock_encrypt = type("Result", (), {"stdout": "", "returncode": 0})()

        def mock_run(cmd, **kwargs):
            if "--decrypt" in cmd:
                return mock_decrypt
            if "--encrypt" in cmd:
                return mock_encrypt
            raise AssertionError(f"Unexpected sops command: {cmd}")

        from unittest.mock import patch

        with patch("infrafoundry.core.config.sops.subprocess.run", side_effect=mock_run):
            result = cli_runner.invoke(
                main,
                [
                    "--config-dir",
                    str(config_dir),
                    "config",
                    "create",
                    "staging",
                    "--from",
                    "dev",
                ],
            )

        assert result.exit_code == 0
        assert "Environment 'staging' created from 'dev'" in result.output

    def test_create_from_unencrypted_settings_unchanged(self, cli_runner, temp_config_dir):
        """Test create --from with unencrypted settings works without SOPS calls."""
        from unittest.mock import patch

        with patch("infrafoundry.core.config.sops.subprocess.run") as mock_run:
            result = cli_runner.invoke(
                main,
                [
                    "--config-dir",
                    str(temp_config_dir),
                    "config",
                    "create",
                    "staging",
                    "--from",
                    "dev",
                ],
            )

        assert result.exit_code == 0
        # SOPS subprocess should not be called for unencrypted files
        mock_run.assert_not_called()

        # Verify settings were updated correctly
        with open(temp_config_dir / "envs" / "staging" / "settings.yaml") as f:
            settings = yaml.safe_load(f)
        assert settings["name"] == "staging"


class TestConfigShow:
    """Tests for config show command."""

    def test_show_displays_environment_info(self, cli_runner, temp_config_dir):
        """Test show displays environment information."""
        result = cli_runner.invoke(
            main,
            ["--config-dir", str(temp_config_dir), "config", "show", "--env", "dev"],
        )

        assert result.exit_code == 0
        assert "dev" in result.output
        assert "Development environment" in result.output or "Description" in result.output

    def test_show_settings_only(self, cli_runner, temp_config_dir):
        """Test show --settings-only displays only settings."""
        result = cli_runner.invoke(
            main,
            [
                "--config-dir",
                str(temp_config_dir),
                "config",
                "show",
                "--env",
                "dev",
                "--settings-only",
            ],
        )

        assert result.exit_code == 0
        assert "dev" in result.output

    def test_show_yaml_format(self, cli_runner, temp_config_dir):
        """Test show --format yaml outputs YAML."""
        result = cli_runner.invoke(
            main,
            [
                "--config-dir",
                str(temp_config_dir),
                "config",
                "show",
                "--env",
                "dev",
                "--format",
                "yaml",
            ],
        )

        assert result.exit_code == 0
        # YAML output should contain these patterns
        assert "environment:" in result.output or "name:" in result.output

    def test_show_json_format(self, cli_runner, temp_config_dir):
        """Test show --format json outputs JSON."""
        result = cli_runner.invoke(
            main,
            [
                "--config-dir",
                str(temp_config_dir),
                "config",
                "show",
                "--env",
                "dev",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0
        # JSON output should contain these patterns
        assert '"environment"' in result.output or '"name"' in result.output

    def test_show_filter_by_provider(self, cli_runner, temp_config_dir):
        """Test show --provider filters resources."""
        result = cli_runner.invoke(
            main,
            [
                "--config-dir",
                str(temp_config_dir),
                "config",
                "show",
                "--env",
                "dev",
                "--provider",
                "proxmox",
            ],
        )

        assert result.exit_code == 0

    def test_show_filter_by_resource_type(self, cli_runner, temp_config_dir):
        """Test show --resource-type filters resources."""
        result = cli_runner.invoke(
            main,
            [
                "--config-dir",
                str(temp_config_dir),
                "config",
                "show",
                "--env",
                "dev",
                "--resource-type",
                "vm",
            ],
        )

        assert result.exit_code == 0

    def test_show_specific_resource(self, cli_runner, temp_config_dir):
        """Test show --resource shows specific resource."""
        result = cli_runner.invoke(
            main,
            [
                "--config-dir",
                str(temp_config_dir),
                "config",
                "show",
                "--env",
                "dev",
                "--resource",
                "test-vm",
            ],
        )

        assert result.exit_code == 0

    def test_show_nonexistent_environment(self, cli_runner, temp_config_dir):
        """Test show with nonexistent environment fails."""
        result = cli_runner.invoke(
            main,
            [
                "--config-dir",
                str(temp_config_dir),
                "config",
                "show",
                "--env",
                "nonexistent",
            ],
        )

        assert result.exit_code != 0

    def test_show_no_matching_resources(self, cli_runner, temp_config_dir):
        """Test show with no matching filter shows warning."""
        result = cli_runner.invoke(
            main,
            [
                "--config-dir",
                str(temp_config_dir),
                "config",
                "show",
                "--env",
                "dev",
                "--provider",
                "nonexistent-provider",
            ],
        )

        assert result.exit_code == 0
        assert "No resources found" in result.output


class TestConfigCreateShowIntegration:
    """Integration tests for create and show commands working together."""

    def test_create_then_show(self, cli_runner, temp_config_dir):
        """Test creating environment with create then viewing with show."""
        # Create new environment from dev
        create_result = cli_runner.invoke(
            main,
            [
                "--config-dir",
                str(temp_config_dir),
                "config",
                "create",
                "staging",
                "--from",
                "dev",
            ],
        )
        assert create_result.exit_code == 0

        # Show the new environment
        show_result = cli_runner.invoke(
            main,
            [
                "--config-dir",
                str(temp_config_dir),
                "config",
                "show",
                "--env",
                "staging",
            ],
        )
        assert show_result.exit_code == 0
        assert "staging" in show_result.output
