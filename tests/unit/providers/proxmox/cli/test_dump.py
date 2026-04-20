"""Unit tests for the ``foundry provider proxmox dump`` CLI command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from infrafoundry.providers.proxmox.cli.dump import dump


@pytest.fixture
def cli_runner():
    """CLI runner for invoking the command."""
    return CliRunner()


@pytest.fixture
def mock_config_manager():
    """Config manager stub returning Proxmox provider settings."""
    mock = Mock()
    mock_env = Mock()
    mock_env.model_dump.return_value = {
        "provider_settings": {
            "proxmox": {
                "api_url": "https://proxmox.example.com:8006/api2/json",
                "api_token": "user@pam!token=secret",
            }
        }
    }
    mock.load_environment.return_value = mock_env
    return mock


@pytest.fixture
def mock_dumper():
    """ProxmoxStateDumper stub returning a canned result dict."""
    mock = Mock()
    mock.dump.return_value = {
        "meta": {"version": {"release": "8.2"}},
        "nodes": ["pve1"],
    }
    return mock


def test_dump_success(cli_runner, tmp_path, mock_config_manager, mock_dumper):
    """Happy-path: dumper is invoked and reports the section count."""
    output_file = tmp_path / "dump.json"

    with (
        patch(
            "infrafoundry.providers.proxmox.cli.dump.ConfigManager",
            return_value=mock_config_manager,
        ),
        patch(
            "infrafoundry.providers.proxmox.cli.dump.ProxmoxStateDumper",
            return_value=mock_dumper,
        ) as dumper_cls,
    ):
        result = cli_runner.invoke(
            dump,
            ["--env", "prod", "--output", str(output_file)],
            obj={"config_dir": Path("/fake/config")},
        )

        assert result.exit_code == 0, result.output
        assert "Dumped 2 sections" in result.output
        # Default timeout is 20.
        dumper_cls.assert_called_once()
        _, kwargs = dumper_cls.call_args
        assert kwargs["timeout"] == 20
        mock_dumper.dump.assert_called_once_with(output_file)


def test_dump_custom_timeout(cli_runner, tmp_path, mock_config_manager, mock_dumper):
    """``--timeout`` is forwarded to the dumper constructor."""
    output_file = tmp_path / "dump.json"

    with (
        patch(
            "infrafoundry.providers.proxmox.cli.dump.ConfigManager",
            return_value=mock_config_manager,
        ),
        patch(
            "infrafoundry.providers.proxmox.cli.dump.ProxmoxStateDumper",
            return_value=mock_dumper,
        ) as dumper_cls,
    ):
        result = cli_runner.invoke(
            dump,
            ["--env", "prod", "--output", str(output_file), "--timeout", "60"],
            obj={"config_dir": Path("/fake/config")},
        )

        assert result.exit_code == 0, result.output
        _, kwargs = dumper_cls.call_args
        assert kwargs["timeout"] == 60


def test_dump_missing_env(cli_runner, tmp_path):
    """Without ``--env`` Click reports a usage error."""
    output_file = tmp_path / "dump.json"
    result = cli_runner.invoke(
        dump,
        ["--output", str(output_file)],
        obj={"config_dir": Path("/fake/config")},
    )
    assert result.exit_code != 0
    assert "Missing option '--env'" in result.output or "Error" in result.output


def test_dump_missing_output(cli_runner):
    """Without ``--output`` Click reports a usage error."""
    result = cli_runner.invoke(
        dump,
        ["--env", "prod"],
        obj={"config_dir": Path("/fake/config")},
    )
    assert result.exit_code != 0
    assert "Missing option '--output'" in result.output or "Error" in result.output


def test_dump_reports_dumper_error(cli_runner, tmp_path, mock_config_manager):
    """Exceptions from the dumper are translated into Click errors."""
    output_file = tmp_path / "dump.json"
    mock_dumper = Mock()
    mock_dumper.dump.side_effect = Exception("API unreachable")

    with (
        patch(
            "infrafoundry.providers.proxmox.cli.dump.ConfigManager",
            return_value=mock_config_manager,
        ),
        patch(
            "infrafoundry.providers.proxmox.cli.dump.ProxmoxStateDumper",
            return_value=mock_dumper,
        ),
    ):
        result = cli_runner.invoke(
            dump,
            ["--env", "prod", "--output", str(output_file)],
            obj={"config_dir": Path("/fake/config")},
        )
        assert result.exit_code != 0
        assert "Failed to dump Proxmox state" in result.output


def test_dump_without_config_dir(cli_runner, tmp_path, mock_dumper):
    """Dump works when no config_dir is in context (falls back to default)."""
    output_file = tmp_path / "dump.json"

    mock_config_manager = Mock()
    mock_env = Mock()
    mock_env.model_dump.return_value = {
        "provider_settings": {
            "proxmox": {
                "api_url": "https://proxmox.example.com:8006/api2/json",
                "api_token": "token",
            }
        }
    }
    mock_config_manager.load_environment.return_value = mock_env

    with (
        patch(
            "infrafoundry.providers.proxmox.cli.dump.ConfigManager",
            return_value=mock_config_manager,
        ),
        patch(
            "infrafoundry.providers.proxmox.cli.dump.ProxmoxStateDumper",
            return_value=mock_dumper,
        ),
    ):
        result = cli_runner.invoke(
            dump,
            ["--env", "prod", "--output", str(output_file)],
            obj={},
        )
        assert result.exit_code == 0, result.output
