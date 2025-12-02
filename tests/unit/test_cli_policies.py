"""Unit tests for the 'policies' CLI command."""

from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from infrafoundry.cli.main import main
from infrafoundry.core.orchestrator import Orchestrator


@pytest.fixture
def cli_runner():
    """Fixture for invoking CLI commands."""
    return CliRunner()


@pytest.fixture
def mock_orchestrator():
    """Mock orchestrator for testing."""
    mock = Mock(spec=Orchestrator)
    mock.policy_engine = Mock()
    return mock


@pytest.fixture
def sample_policies():
    """Sample policy data."""
    policy1 = Mock()
    policy1.name = "naming_convention"
    policy1.type = Mock(value="validation")
    policy1.level = Mock(value="warning")
    policy1.enabled = True
    policy1.environments = ["dev", "test"]
    policy1.description = "Enforce naming conventions"

    policy2 = Mock()
    policy2.name = "resource_limits"
    policy2.type = Mock(value="validation")
    policy2.level = Mock(value="error")
    policy2.enabled = True
    policy2.environments = []
    policy2.description = "Enforce resource limits"

    return [policy1, policy2]


def test_policies_list_all(cli_runner, mock_orchestrator, sample_policies):
    """Test policies command lists all policies."""
    mock_orchestrator.policy_engine.policies = sample_policies

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["policies"])

        assert result.exit_code == 0
        assert "All Policies" in result.output
        # Check for partial matches since rich may truncate text in tables
        assert "naming" in result.output or "convention" in result.output
        assert "resource" in result.output or "limits" in result.output
        assert "Total: 2" in result.output


def test_policies_list_for_environment(cli_runner, mock_orchestrator, sample_policies):
    """Test policies command for specific environment."""
    mock_orchestrator.policy_engine.get_policies_for_environment.return_value = [sample_policies[0]]

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["policies", "--env", "dev"])

        assert result.exit_code == 0
        assert "Policies for dev" in result.output
        # Check for partial match since rich may truncate text
        assert "naming" in result.output or "convention" in result.output
        mock_orchestrator.policy_engine.get_policies_for_environment.assert_called_once_with("dev")


def test_policies_no_policies_found(cli_runner, mock_orchestrator):
    """Test policies command when no policies are found."""
    mock_orchestrator.policy_engine.policies = []

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["policies"])

        assert result.exit_code == 0
        assert "No policies found" in result.output
        assert "Create policy files in the 'policies' directory" in result.output
