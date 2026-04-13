"""Unit tests for the enhanced config envs command with sync status."""

from __future__ import annotations

import json
from unittest.mock import patch

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
    """Create a temporary config directory with two environments."""
    config_dir = tmp_path / "config"
    envs_dir = config_dir / "envs"

    # Create dev environment
    dev_dir = envs_dir / "dev"
    dev_dir.mkdir(parents=True)
    settings = {
        "name": "dev",
        "description": "Development environment",
        "providers": ["proxmox"],
    }
    (dev_dir / "settings.yaml").write_text(yaml.safe_dump(settings))

    # Create prod environment
    prod_dir = envs_dir / "prod"
    prod_dir.mkdir(parents=True)
    settings = {
        "name": "prod",
        "description": "Production environment",
        "providers": ["proxmox", "opnsense"],
    }
    (prod_dir / "settings.yaml").write_text(yaml.safe_dump(settings))

    return config_dir


class TestConfigEnvsSyncStatus:
    """Tests for config envs sync status display."""

    def test_fs_only_env_shows_status(self, cli_runner: CliRunner, temp_config_dir) -> None:
        """FS-only environment shows FS-ONLY status."""
        with patch(
            "infrafoundry.cli.commands.config.envs._get_state_db_environments",
            return_value=([], {}, True),
        ):
            result = cli_runner.invoke(main, ["-c", str(temp_config_dir), "config", "envs"])
            assert result.exit_code == 0
            assert "FS-ONLY" in result.output

    def test_db_only_env_shows_status(self, cli_runner: CliRunner, temp_config_dir) -> None:
        """DB-only environment shows DB-ONLY status."""
        with patch(
            "infrafoundry.cli.commands.config.envs._get_state_db_environments",
            return_value=(["hl", "hl-test"], {"hl": 5, "hl-test": 3}, True),
        ):
            result = cli_runner.invoke(main, ["-c", str(temp_config_dir), "config", "envs"])
            assert result.exit_code == 0
            assert "DB-ONLY" in result.output

    def test_consistent_env_shows_ok(self, cli_runner: CliRunner, temp_config_dir) -> None:
        """Environment in both sources shows OK status."""
        with patch(
            "infrafoundry.cli.commands.config.envs._get_state_db_environments",
            return_value=(["dev"], {"dev": 2}, True),
        ):
            result = cli_runner.invoke(main, ["-c", str(temp_config_dir), "config", "envs"])
            assert result.exit_code == 0
            assert "OK" in result.output

    def test_state_db_unavailable_degrades_gracefully(
        self, cli_runner: CliRunner, temp_config_dir
    ) -> None:
        """State DB unavailable shows warning and FS environments."""
        with patch(
            "infrafoundry.cli.commands.config.envs._get_state_db_environments",
            return_value=([], {}, False),
        ):
            result = cli_runner.invoke(main, ["-c", str(temp_config_dir), "config", "envs"])
            assert result.exit_code == 0
            assert "State database unavailable" in result.output
            assert "dev" in result.output
            assert "prod" in result.output

    def test_json_output_includes_sync_status(self, cli_runner: CliRunner, temp_config_dir) -> None:
        """JSON output includes sync_status field per environment."""
        with patch(
            "infrafoundry.cli.commands.config.envs._get_state_db_environments",
            return_value=(["dev", "hl"], {"dev": 2, "hl": 5}, True),
        ):
            result = cli_runner.invoke(
                main,
                ["-c", str(temp_config_dir), "config", "envs", "--format", "json"],
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert "environments" in data
            assert data["state_db_available"] is True

            envs_by_name = {e["name"]: e for e in data["environments"]}
            assert envs_by_name["dev"]["sync_status"] == "ok"
            assert envs_by_name["prod"]["sync_status"] == "fs_only"
            assert envs_by_name["hl"]["sync_status"] == "db_only"

    def test_json_output_db_unavailable(self, cli_runner: CliRunner, temp_config_dir) -> None:
        """JSON output includes state_db_available flag."""
        with patch(
            "infrafoundry.cli.commands.config.envs._get_state_db_environments",
            return_value=([], {}, False),
        ):
            result = cli_runner.invoke(
                main,
                ["-c", str(temp_config_dir), "config", "envs", "--format", "json"],
            )
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["state_db_available"] is False

    def test_no_environments_found(self, cli_runner: CliRunner, tmp_path) -> None:
        """No environments anywhere shows appropriate message."""
        config_dir = tmp_path / "empty"
        envs_dir = config_dir / "envs"
        envs_dir.mkdir(parents=True)

        with patch(
            "infrafoundry.cli.commands.config.envs._get_state_db_environments",
            return_value=([], {}, True),
        ):
            result = cli_runner.invoke(main, ["-c", str(config_dir), "config", "envs"])
            assert result.exit_code == 0
            assert "No environments found" in result.output

    def test_resource_count_shown_for_db_envs(self, cli_runner: CliRunner, temp_config_dir) -> None:
        """Tracked resource count shown for environments with DB records."""
        with patch(
            "infrafoundry.cli.commands.config.envs._get_state_db_environments",
            return_value=(["dev"], {"dev": 7}, True),
        ):
            result = cli_runner.invoke(main, ["-c", str(temp_config_dir), "config", "envs"])
            assert result.exit_code == 0
            assert "Tracked resources: 7" in result.output
