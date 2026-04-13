"""Unit tests for the config check command."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
import yaml
from click.testing import CliRunner

from infrafoundry.cli.main import main

# All tests mock the shared _get_state_db_environments helper (defined in envs.py,
# imported by check.py).  We patch it on the check module's namespace.
_MOCK_TARGET = "infrafoundry.cli.commands.config.check._get_state_db_environments"


@pytest.fixture
def cli_runner():
    """Fixture for invoking CLI commands."""
    return CliRunner()


@pytest.fixture
def temp_config_dir(tmp_path):
    """Create a temporary config directory with two environments."""
    config_dir = tmp_path / "config"
    envs_dir = config_dir / "envs"

    for env_name in ("dev", "prod"):
        env_dir = envs_dir / env_name
        env_dir.mkdir(parents=True)
        settings = {
            "name": env_name,
            "description": f"{env_name} environment",
            "providers": ["proxmox"],
        }
        (env_dir / "settings.yaml").write_text(yaml.safe_dump(settings))

    return config_dir


class TestConfigCheck:
    """Tests for config check command."""

    def test_clean_state_exits_0(self, cli_runner: CliRunner, temp_config_dir) -> None:
        """Clean state (all consistent) exits with code 0."""
        with patch(_MOCK_TARGET, return_value=(["dev", "prod"], {"dev": 0, "prod": 0}, True)):
            result = cli_runner.invoke(main, ["-c", str(temp_config_dir), "config", "check"])
            assert result.exit_code == 0
            assert "consistent" in result.output.lower()

    def test_mismatch_exits_1(self, cli_runner: CliRunner, temp_config_dir) -> None:
        """Mismatch between filesystem and state DB exits with code 1."""
        with patch(_MOCK_TARGET, return_value=(["dev", "hl"], {"dev": 0, "hl": 0}, True)):
            result = cli_runner.invoke(main, ["-c", str(temp_config_dir), "config", "check"])
            assert result.exit_code == 1
            assert "FAILED" in result.output

    def test_fs_only_reported(self, cli_runner: CliRunner, temp_config_dir) -> None:
        """Filesystem-only environments are reported."""
        with patch(_MOCK_TARGET, return_value=([], {}, True)):
            result = cli_runner.invoke(main, ["-c", str(temp_config_dir), "config", "check"])
            assert result.exit_code == 1
            assert "Filesystem only" in result.output
            assert "dev" in result.output

    def test_db_only_reported(self, cli_runner: CliRunner, temp_config_dir) -> None:
        """State DB-only environments are reported."""
        with patch(
            _MOCK_TARGET,
            return_value=(["dev", "prod", "hl-test"], {"dev": 0, "prod": 0, "hl-test": 0}, True),
        ):
            result = cli_runner.invoke(main, ["-c", str(temp_config_dir), "config", "check"])
            assert result.exit_code == 1
            assert "State DB only" in result.output
            assert "hl-test" in result.output

    def test_json_format_output_structure(self, cli_runner: CliRunner, temp_config_dir) -> None:
        """JSON output has expected structure."""
        with patch(_MOCK_TARGET, return_value=(["dev", "hl"], {"dev": 0, "hl": 0}, True)):
            result = cli_runner.invoke(
                main,
                ["-c", str(temp_config_dir), "config", "check", "--format", "json"],
            )
            # JSON is always printed regardless of exit code
            data = json.loads(result.output)
            assert data["state_db_available"] is True
            assert "dev" in data["consistent"]
            assert "prod" in data["fs_only"]
            assert "hl" in data["db_only"]
            assert data["has_issues"] is True

    def test_json_clean_state(self, cli_runner: CliRunner, temp_config_dir) -> None:
        """JSON output for clean state shows has_issues=False."""
        with patch(_MOCK_TARGET, return_value=(["dev", "prod"], {"dev": 0, "prod": 0}, True)):
            result = cli_runner.invoke(
                main,
                ["-c", str(temp_config_dir), "config", "check", "--format", "json"],
            )
            data = json.loads(result.output)
            assert data["has_issues"] is False
            assert data["fs_only"] == []
            assert data["db_only"] == []

    def test_state_db_unavailable(self, cli_runner: CliRunner, temp_config_dir) -> None:
        """State DB unavailable shows warning, does not fail."""
        with patch(_MOCK_TARGET, return_value=([], {}, False)):
            result = cli_runner.invoke(main, ["-c", str(temp_config_dir), "config", "check"])
            assert result.exit_code == 0
            assert "unavailable" in result.output.lower()

    def test_deep_flag_shows_resource_counts(self, cli_runner: CliRunner, temp_config_dir) -> None:
        """--deep flag includes resource counts in output."""
        with patch(_MOCK_TARGET, return_value=(["dev", "prod"], {"dev": 5, "prod": 12}, True)):
            result = cli_runner.invoke(
                main,
                ["-c", str(temp_config_dir), "config", "check", "--deep"],
            )
            assert result.exit_code == 0
            assert "5 resource(s)" in result.output
            assert "12 resource(s)" in result.output

    def test_deep_json_includes_counts(self, cli_runner: CliRunner, temp_config_dir) -> None:
        """--deep with JSON includes resource_counts dict."""
        with patch(_MOCK_TARGET, return_value=(["dev", "prod"], {"dev": 5, "prod": 12}, True)):
            result = cli_runner.invoke(
                main,
                [
                    "-c",
                    str(temp_config_dir),
                    "config",
                    "check",
                    "--deep",
                    "--format",
                    "json",
                ],
            )
            data = json.loads(result.output)
            assert data["resource_counts"] == {"dev": 5, "prod": 12}
