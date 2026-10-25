"""Unit tests for the 'graph' CLI command."""

from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from infrafoundry.cli.main import main
from infrafoundry.core.orchestrator import Orchestrator


@pytest.fixture
def cli_runner() -> CliRunner:
    """Fixture for invoking CLI commands."""
    return CliRunner()


@pytest.fixture
def mock_orchestrator() -> Mock:
    """Mock orchestrator for testing."""
    mock = Mock(spec=Orchestrator)
    return mock


@pytest.fixture
def mock_dependency_graph() -> Mock:
    """Mock dependency graph."""
    mock = Mock()
    mock.export_to_mermaid.return_value = "graph TD\n  A --> B\n  B --> C"
    return mock


def test_graph_mermaid_format(
    cli_runner: CliRunner, mock_orchestrator: Mock, mock_dependency_graph: Mock
) -> None:
    """Test graph command with mermaid format."""
    mock_orchestrator.build_dependency_graph.return_value = mock_dependency_graph

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["infra", "analyze", "graph", "--env", "test"])

        assert result.exit_code == 0
        assert "graph TD" in result.output
        mock_orchestrator.build_dependency_graph.assert_called_once_with("test")
        mock_dependency_graph.export_to_mermaid.assert_called_once()


def test_graph_explicit_mermaid_format(
    cli_runner: CliRunner, mock_orchestrator: Mock, mock_dependency_graph: Mock
) -> None:
    """Test graph command with explicit mermaid format flag."""
    mock_orchestrator.build_dependency_graph.return_value = mock_dependency_graph

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main, ["infra", "analyze", "graph", "--env", "test", "--format", "mermaid"]
        )

        assert result.exit_code == 0
        assert "graph TD" in result.output


def test_graph_orchestrator_failure(cli_runner: CliRunner, mock_orchestrator: Mock) -> None:
    """Test graph command when orchestrator.build_dependency_graph raises an error."""
    mock_orchestrator.build_dependency_graph.side_effect = Exception("Graph generation failed")

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["infra", "analyze", "graph", "--env", "test"])

        assert result.exit_code == 1
        assert "Graph generation failed" in result.output
