"""Unit tests for the 'new' CLI command group."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from infrafoundry.cli.main import main


@pytest.fixture
def cli_runner():
    """Fixture for invoking CLI commands."""
    return CliRunner()


@pytest.fixture
def mock_blueprint_manager():
    """Mock BlueprintManager for testing."""
    from infrafoundry.core.blueprints import BlueprintManager

    mock = Mock(spec=BlueprintManager)
    return mock


@pytest.fixture
def sample_blueprints():
    """Sample blueprint data."""
    bp1 = Mock()
    bp1.name = "basic-vm"
    bp1.description = "Basic VM configuration"
    bp1.version = "1.0.0"

    bp2 = Mock()
    bp2.name = "kubernetes-cluster"
    bp2.description = "Kubernetes cluster setup"
    bp2.version = "2.0.0"

    return [bp1, bp2]


def test_new_list_blueprints(cli_runner, mock_blueprint_manager, sample_blueprints):
    """Test new command lists available blueprints."""
    mock_blueprint_manager.list_blueprints.return_value = sample_blueprints

    with patch(
        "infrafoundry.cli.commands.new.BlueprintManager", return_value=mock_blueprint_manager
    ):
        result = cli_runner.invoke(main, ["new"])

        assert result.exit_code == 0
        assert "Available Blueprints" in result.output
        assert "basic-vm" in result.output
        assert "kubernetes-cluster" in result.output


def test_new_no_blueprints(cli_runner, mock_blueprint_manager):
    """Test new command when no blueprints are found."""
    mock_blueprint_manager.list_blueprints.return_value = []

    with patch(
        "infrafoundry.cli.commands.new.BlueprintManager", return_value=mock_blueprint_manager
    ):
        result = cli_runner.invoke(main, ["new"])

        assert result.exit_code == 0
        assert "No blueprints found" in result.output


def test_new_create_blueprint(cli_runner, mock_blueprint_manager, tmp_path):
    """Test new create command."""
    target_dir = tmp_path / "new-project"

    with patch(
        "infrafoundry.cli.commands.new.BlueprintManager", return_value=mock_blueprint_manager
    ):
        result = cli_runner.invoke(main, ["config", "new", "create", "basic-vm", str(target_dir)])

        assert result.exit_code == 0
        assert "Successfully created project" in result.output
        mock_blueprint_manager.instantiate_blueprint.assert_called_once_with(
            "basic-vm", Path(str(target_dir)), context={}
        )


def test_new_create_blueprint_not_found(cli_runner, mock_blueprint_manager, tmp_path):
    """Test new create command when blueprint doesn't exist."""
    target_dir = tmp_path / "new-project"
    mock_blueprint_manager.instantiate_blueprint.side_effect = ValueError("Blueprint not found")

    with patch(
        "infrafoundry.cli.commands.new.BlueprintManager", return_value=mock_blueprint_manager
    ):
        result = cli_runner.invoke(
            main, ["config", "new", "create", "nonexistent", str(target_dir)]
        )

        assert result.exit_code == 0  # Error is caught and printed
        assert "Error:" in result.output


def test_new_create_blueprint_unexpected_error(cli_runner, mock_blueprint_manager, tmp_path):
    """Test new create command with unexpected error."""
    target_dir = tmp_path / "new-project"
    mock_blueprint_manager.instantiate_blueprint.side_effect = Exception("Unexpected error")

    with patch(
        "infrafoundry.cli.commands.new.BlueprintManager", return_value=mock_blueprint_manager
    ):
        result = cli_runner.invoke(main, ["config", "new", "create", "basic-vm", str(target_dir)])

        assert result.exit_code == 0  # Error is caught and printed
        assert "Unexpected error:" in result.output
