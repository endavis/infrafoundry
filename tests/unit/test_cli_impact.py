"""Unit tests for the 'impact' CLI command."""

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
    return mock


@pytest.fixture
def mock_dependency_graph():
    """Mock dependency graph."""
    mock = Mock()
    mock.nodes = {"proxmox:vm-01": None, "proxmox:vm-02": None}
    return mock


def test_impact_low_risk(cli_runner, mock_orchestrator, mock_dependency_graph):
    """Test impact command with low risk resource."""
    analysis = {
        "risk_level": "LOW",
        "direct_dependents": 0,
        "total_dependents": 0,
        "dependent_resources": [],
    }
    mock_dependency_graph.get_impact_analysis.return_value = analysis
    mock_orchestrator.build_dependency_graph.return_value = mock_dependency_graph

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main, ["analyze", "impact", "--env", "test", "--resource", "vm-01"]
        )

        assert result.exit_code == 0
        assert "Impact Analysis for: vm-01" in result.output
        assert "LOW" in result.output
        assert "No other resources depend on this" in result.output
        mock_orchestrator.build_dependency_graph.assert_called_once_with("test")
        mock_dependency_graph.get_impact_analysis.assert_called_once_with("proxmox:vm-01")


def test_impact_medium_risk(cli_runner, mock_orchestrator, mock_dependency_graph):
    """Test impact command with medium risk resource."""
    analysis = {
        "risk_level": "MEDIUM",
        "direct_dependents": 2,
        "total_dependents": 3,
        "dependent_resources": ["proxmox:vm-02", "proxmox:vm-03"],
    }
    mock_dependency_graph.get_impact_analysis.return_value = analysis
    mock_orchestrator.build_dependency_graph.return_value = mock_dependency_graph

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main, ["analyze", "impact", "--env", "test", "--resource", "vm-01"]
        )

        assert result.exit_code == 0
        assert "MEDIUM" in result.output
        assert "3 resource(s) may be affected" in result.output
        assert "proxmox:vm-02" in result.output


def test_impact_high_risk(cli_runner, mock_orchestrator, mock_dependency_graph):
    """Test impact command with high risk resource."""
    analysis = {
        "risk_level": "HIGH",
        "direct_dependents": 5,
        "total_dependents": 8,
        "dependent_resources": ["proxmox:vm-02", "proxmox:vm-03", "opnsense:firewall-01"],
    }
    mock_dependency_graph.get_impact_analysis.return_value = analysis
    mock_orchestrator.build_dependency_graph.return_value = mock_dependency_graph

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main, ["analyze", "impact", "--env", "test", "--resource", "vm-01"]
        )

        assert result.exit_code == 0
        assert "HIGH" in result.output
        assert "8 resource(s) will be affected" in result.output


def test_impact_resource_not_found(cli_runner, mock_orchestrator, mock_dependency_graph):
    """Test impact command when resource is not found."""
    mock_dependency_graph.get_impact_analysis.return_value = {"error": "not found"}
    mock_orchestrator.build_dependency_graph.return_value = mock_dependency_graph

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main, ["analyze", "impact", "--env", "test", "--resource", "nonexistent"]
        )

        assert result.exit_code == 0
        assert "Resource 'nonexistent' not found" in result.output
        assert "Available resources:" in result.output


def test_impact_orchestrator_failure(cli_runner, mock_orchestrator):
    """Test impact command when orchestrator.build_dependency_graph raises an error."""
    mock_orchestrator.build_dependency_graph.side_effect = Exception("Impact analysis failed")

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main, ["analyze", "impact", "--env", "test", "--resource", "vm-01"]
        )

        assert result.exit_code == 1
        assert "Impact analysis failed" in result.output
