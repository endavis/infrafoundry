"""Unit tests for the 'deployed' CLI command."""

import json
from datetime import datetime
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from infrafoundry.cli.main import main
from infrafoundry.core.orchestrator import Orchestrator
from infrafoundry.core.state import DeploymentStatus
from infrafoundry.core.state.models import ResourceState


@pytest.fixture
def cli_runner():
    """Fixture for invoking CLI commands."""
    return CliRunner()


@pytest.fixture
def mock_orchestrator():
    """Mock orchestrator for testing."""
    mock = Mock(spec=Orchestrator)
    mock.state_manager = Mock()
    return mock


@pytest.fixture
def sample_deployment():
    """A single completed apply deployment."""
    dep = Mock()
    dep.id = 42
    dep.environment = "prod"
    dep.command = "apply"
    dep.status = DeploymentStatus.COMPLETED
    dep.dry_run = False
    dep.started_at = datetime(2026, 4, 12, 16, 45, 0)
    dep.completed_at = datetime(2026, 4, 12, 16, 48, 0)
    dep.user = "endavis"
    return dep


@pytest.fixture
def sample_resources():
    """Sample resources across two providers."""
    r1 = Mock()
    r1.name = "aiqum"
    r1.provider = "proxmox"
    r1.resource_type = "vm"
    r1.state = ResourceState.ACTIVE
    r1.config = {"ip_address": "192.168.10.206", "target_node": "pve1"}
    r1.updated_at = datetime(2026, 4, 12, 14, 30, 0)

    r2 = Mock()
    r2.name = "ontap-node01"
    r2.provider = "proxmox"
    r2.resource_type = "vm"
    r2.state = ResourceState.ACTIVE
    r2.config = {"ip_address": "192.168.10.203", "target_node": "pve1"}
    r2.updated_at = datetime(2026, 4, 11, 9, 15, 0)

    r3 = Mock()
    r3.name = "dhcp-aiqum"
    r3.provider = "opnsense"
    r3.resource_type = "dhcp"
    r3.state = ResourceState.ACTIVE
    r3.config = {}
    r3.updated_at = datetime(2026, 4, 12, 14, 30, 0)

    return [r1, r2, r3]


def test_deployed_shows_deployment_info(
    cli_runner, mock_orchestrator, sample_deployment, sample_resources
):
    """Test that deployed command shows latest deployment info and resources."""
    mock_orchestrator.state_manager.get_deployment_history.return_value = [sample_deployment]
    mock_orchestrator.state_manager.get_resources.return_value = sample_resources

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["infra", "deployed", "--env", "prod"])

    assert result.exit_code == 0, f"Exit code {result.exit_code}. Output: {result.output}"
    assert "Environment: prod" in result.output
    assert "completed" in result.output
    assert "2026-04-12 16:45" in result.output
    assert "2026-04-12 16:48" in result.output
    assert "endavis" in result.output
    assert "aiqum" in result.output
    assert "192.168.10.206" in result.output
    assert "pve1" in result.output
    assert "dhcp-aiqum" in result.output
    assert "2026-04-12 14:30" in result.output
    assert "2026-04-11 09:15" in result.output

    mock_orchestrator.state_manager.get_deployment_history.assert_called_once_with(
        environment="prod",
        command="apply",
        exclude_dry_run=True,
        limit=1,
    )
    mock_orchestrator.state_manager.get_resources.assert_called_once_with(environment="prod")


def test_deployed_no_deployments(cli_runner, mock_orchestrator):
    """Test deployed command when no deployments exist."""
    mock_orchestrator.state_manager.get_deployment_history.return_value = []
    mock_orchestrator.state_manager.get_resources.return_value = []

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["infra", "deployed", "--env", "staging"])

    assert result.exit_code == 0, f"Exit code {result.exit_code}. Output: {result.output}"
    assert "No deployments found for environment 'staging'" in result.output
    assert "No tracked resources for environment 'staging'" in result.output


def test_deployed_no_resources(cli_runner, mock_orchestrator, sample_deployment):
    """Test deployed command when deployment exists but no resources tracked."""
    mock_orchestrator.state_manager.get_deployment_history.return_value = [sample_deployment]
    mock_orchestrator.state_manager.get_resources.return_value = []

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["infra", "deployed", "--env", "prod"])

    assert result.exit_code == 0, f"Exit code {result.exit_code}. Output: {result.output}"
    assert "completed" in result.output
    assert "No tracked resources for environment 'prod'" in result.output


def test_deployed_json_output(cli_runner, mock_orchestrator, sample_deployment, sample_resources):
    """Test JSON output has correct structure."""
    mock_orchestrator.state_manager.get_deployment_history.return_value = [sample_deployment]
    mock_orchestrator.state_manager.get_resources.return_value = sample_resources

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["infra", "deployed", "--env", "prod", "--format", "json"])

    assert result.exit_code == 0, f"Exit code {result.exit_code}. Output: {result.output}"
    data = json.loads(result.output)

    assert data["environment"] == "prod"
    assert data["last_deployment"]["id"] == 42
    assert data["last_deployment"]["status"] == "completed"
    assert data["last_deployment"]["user"] == "endavis"
    assert "proxmox" in data["resources"]
    assert "opnsense" in data["resources"]
    assert len(data["resources"]["proxmox"]) == 2
    assert len(data["resources"]["opnsense"]) == 1
    assert data["resources"]["proxmox"][0]["updated"] == "2026-04-12 14:30"
    assert data["resources"]["opnsense"][0]["updated"] == "2026-04-12 14:30"


def test_deployed_json_no_deployments(cli_runner, mock_orchestrator):
    """Test JSON output when no deployments exist."""
    mock_orchestrator.state_manager.get_deployment_history.return_value = []
    mock_orchestrator.state_manager.get_resources.return_value = []

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main, ["infra", "deployed", "--env", "staging", "--format", "json"]
        )

    assert result.exit_code == 0, f"Exit code {result.exit_code}. Output: {result.output}"
    data = json.loads(result.output)

    assert data["environment"] == "staging"
    assert data["last_deployment"] is None
    assert data["resources"] == {}


def test_deployed_missing_ip_and_node(cli_runner, mock_orchestrator, sample_deployment):
    """Test that missing IP/node fields show dash placeholder."""
    resource = Mock()
    resource.name = "some-service"
    resource.provider = "cloudflare"
    resource.resource_type = "dns"
    resource.state = ResourceState.ACTIVE
    resource.config = {"zone": "example.com"}
    resource.updated_at = datetime(2026, 4, 10, 8, 0, 0)

    mock_orchestrator.state_manager.get_deployment_history.return_value = [sample_deployment]
    mock_orchestrator.state_manager.get_resources.return_value = [resource]

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["infra", "deployed", "--env", "prod"])

    assert result.exit_code == 0, f"Exit code {result.exit_code}. Output: {result.output}"
    assert "some-service" in result.output
    assert "2026-04-10 08:00" in result.output
    # Em dash used for missing fields
    assert "\u2014" in result.output


def test_deployed_null_config(cli_runner, mock_orchestrator, sample_deployment):
    """Test resource with None config does not crash."""
    resource = Mock()
    resource.name = "orphan"
    resource.provider = "proxmox"
    resource.resource_type = "vm"
    resource.state = ResourceState.ACTIVE
    resource.config = None
    resource.updated_at = None

    mock_orchestrator.state_manager.get_deployment_history.return_value = [sample_deployment]
    mock_orchestrator.state_manager.get_resources.return_value = [resource]

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["infra", "deployed", "--env", "prod"])

    assert result.exit_code == 0, f"Exit code {result.exit_code}. Output: {result.output}"
    assert "orphan" in result.output
    # Em dash for missing updated_at
    assert "\u2014" in result.output


def test_deployed_state_error(cli_runner, mock_orchestrator):
    """Test handling of state DB not initialized."""
    from infrafoundry.core.exceptions import StateError

    mock_orchestrator.state_manager.get_deployment_history.side_effect = StateError(
        "no such table: deployments"
    )

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["infra", "deployed", "--env", "prod"])

    assert result.exit_code != 0
    assert "infra init" in result.output


def test_deployed_requires_env(cli_runner, mock_orchestrator):
    """Test that --env is required."""
    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["infra", "deployed"])

    assert result.exit_code != 0
    assert "Missing option" in result.output or "required" in result.output.lower()


def test_deployed_alternative_ip_keys(cli_runner, mock_orchestrator, sample_deployment):
    """Test that alternative config keys (address, ip, node) are recognized."""
    r1 = Mock()
    r1.name = "host-with-address"
    r1.provider = "custom"
    r1.resource_type = "server"
    r1.state = ResourceState.ACTIVE
    r1.config = {"address": "10.0.0.5", "node": "node3"}
    r1.updated_at = datetime(2026, 4, 13, 12, 0, 0)

    mock_orchestrator.state_manager.get_deployment_history.return_value = [sample_deployment]
    mock_orchestrator.state_manager.get_resources.return_value = [r1]

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(main, ["infra", "deployed", "--env", "prod"])

    assert result.exit_code == 0, f"Exit code {result.exit_code}. Output: {result.output}"
    assert "10.0.0.5" in result.output
    assert "node3" in result.output
