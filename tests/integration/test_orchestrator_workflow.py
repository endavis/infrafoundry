"""Integration tests for Orchestrator workflows."""

from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.events import EventManager
from infrafoundry.core.orchestrator import Orchestrator
from infrafoundry.core.secrets.secret_manager import SecretManager
from infrafoundry.core.state import StateManager


@pytest.fixture
def mock_secret_manager(mock_secrets_dir):
    """Create a mock SecretManager."""
    with patch(
        "infrafoundry.core.secrets.secret_manager.SecretManager.__init__", return_value=None
    ):
        with patch(
            "infrafoundry.core.secrets.secret_manager.SecretManager.__init__", return_value=None
        ):
            manager = SecretManager(env_name="dev", secrets_dir=mock_secrets_dir)
            # Mock decrypt to return simple data
            manager.decrypt_file = MagicMock(return_value={"api_token": "test-token"})
            return manager


@pytest.mark.integration
class TestOrchestratorWorkflow:
    """Integration tests for complete workflows."""

    def test_orchestrator_initialization(
        self, mock_config_dir, mock_secret_manager, mock_policy_dir, temp_dir
    ):
        """Test Orchestrator initialization with all components."""
        config = ConfigManager(mock_config_dir / "envs")
        output_dir = temp_dir / "output"
        state_dir = temp_dir / "state"
        state_dir.mkdir()

        # Create StateManager with proper SQLite connection string
        state_db = state_dir / "state.db"
        state_manager = StateManager(f"sqlite:///{state_db}")
        state_manager.initialize()

        orchestrator = Orchestrator(
            config_manager=config,
            output_dir=output_dir,
            state_manager=state_manager,
            event_manager=EventManager(),
            policy_dir=mock_policy_dir,
        )

        assert orchestrator is not None
        assert orchestrator.config_manager == config
        assert orchestrator.event_manager is not None
        assert orchestrator.state_manager is not None
        assert orchestrator.policy_engine is not None
        assert orchestrator.output_dir == output_dir

    def test_load_environment_configuration(self, mock_config_dir, mock_secret_manager, temp_dir):
        """Test loading environment configuration."""
        config = ConfigManager(mock_config_dir / "envs")
        output_dir = temp_dir / "output"

        Orchestrator(
            config_manager=config,
            output_dir=output_dir,
        )

        # Load environment
        env = config.load_environment("dev")
        assert env is not None
        assert env.name == "dev"
        assert env.description == "Development environment"
        assert "datacenter" in env.variables

    def test_get_resources_from_config(self, mock_config_dir, mock_secret_manager, temp_dir):
        """Test retrieving resources from configuration."""
        config = ConfigManager(mock_config_dir / "envs")
        output_dir = temp_dir / "output"

        Orchestrator(
            config_manager=config,
            output_dir=output_dir,
        )

        # Get resources for proxmox provider
        resources = config.get_all_resources("dev", "proxmox")
        assert resources is not None
        assert len(resources) > 0

    def test_event_system_integration(
        self, mock_config_dir, mock_secret_manager, mock_policy_dir, temp_dir
    ):
        """Test that event system is integrated."""
        config = ConfigManager(mock_config_dir / "envs")
        output_dir = temp_dir / "output"

        event_manager = EventManager()
        events_received = []

        def event_handler(event):
            events_received.append(event.event_type)

        # Subscribe to all events
        event_manager.subscribe_all(event_handler)

        orchestrator = Orchestrator(
            config_manager=config,
            output_dir=output_dir,
            event_manager=event_manager,
            policy_dir=mock_policy_dir,
        )

        # Event manager should be set up
        assert orchestrator.event_manager is not None
        assert orchestrator.event_manager == event_manager

    def test_policy_engine_loaded(
        self, mock_config_dir, mock_secret_manager, mock_policy_dir, temp_dir
    ):
        """Test that policy engine loads policies."""
        config = ConfigManager(mock_config_dir / "envs")
        output_dir = temp_dir / "output"

        orchestrator = Orchestrator(
            config_manager=config,
            output_dir=output_dir,
            policy_dir=mock_policy_dir,
        )

        # Policy engine should be loaded with policies
        assert orchestrator.policy_engine is not None
        policies = orchestrator.policy_engine.policies
        assert len(policies) > 0

        # Verify specific policies exist
        policy_names = {p.name for p in policies}
        assert "resource_limits" in policy_names
        assert "require_tags" in policy_names

    def test_state_tracking_integration(self, mock_config_dir, mock_secret_manager, temp_dir):
        """Test state tracking functionality."""
        config = ConfigManager(mock_config_dir / "envs")
        output_dir = temp_dir / "output"
        state_dir = temp_dir / "state"
        state_dir.mkdir()

        state_db = state_dir / "state.db"
        state_manager = StateManager(f"sqlite:///{state_db}")
        state_manager.initialize()

        orchestrator = Orchestrator(
            config_manager=config,
            output_dir=output_dir,
            state_manager=state_manager,
        )

        # Create a deployment record
        deployment_id = orchestrator.state_manager.create_deployment(
            environment="dev",
            command="plan",
            user="test-user",
        )

        assert deployment_id is not None

        # Verify deployment was tracked
        deployment = orchestrator.state_manager.get_deployment_by_id(deployment_id)
        assert deployment is not None
        assert deployment.environment == "dev"
        assert deployment.command == "plan"
        assert deployment.user == "test-user"

    def test_output_directory_created(self, mock_config_dir, mock_secret_manager, temp_dir):
        """Test that output directory is created automatically."""
        config = ConfigManager(mock_config_dir / "envs")
        output_dir = temp_dir / "custom_output"

        orchestrator = Orchestrator(
            config_manager=config,
            output_dir=output_dir,
        )

        # Output directory should be created
        assert output_dir.exists()
        assert output_dir.is_dir()
        assert orchestrator.output_dir == output_dir

    def test_notification_manager_integration(self, mock_config_dir, mock_secret_manager, temp_dir):
        """Test that notification manager is initialized."""
        config = ConfigManager(mock_config_dir / "envs")
        output_dir = temp_dir / "output"

        orchestrator = Orchestrator(
            config_manager=config,
            output_dir=output_dir,
        )

        # Notification manager should exist
        assert orchestrator.notification_manager is not None

    def test_default_state_manager_created(self, mock_config_dir, mock_secret_manager, temp_dir):
        """Test that default state manager is created if not provided."""
        config = ConfigManager(mock_config_dir / "envs")
        output_dir = temp_dir / "output"

        orchestrator = Orchestrator(
            config_manager=config,
            output_dir=output_dir,
        )

        # Default state manager should be created
        assert orchestrator.state_manager is not None

    def test_default_event_manager_created(self, mock_config_dir, mock_secret_manager, temp_dir):
        """Test that default event manager is created if not provided."""
        config = ConfigManager(mock_config_dir / "envs")
        output_dir = temp_dir / "output"

        orchestrator = Orchestrator(
            config_manager=config,
            output_dir=output_dir,
        )

        # Default event manager should be created
        assert orchestrator.event_manager is not None

    def test_provider_registry_initialized(self, mock_config_dir, mock_secret_manager, temp_dir):
        """Test that provider registry is initialized."""
        config = ConfigManager(mock_config_dir / "envs")
        output_dir = temp_dir / "output"

        orchestrator = Orchestrator(
            config_manager=config,
            output_dir=output_dir,
        )

        # Providers dict should exist and be empty initially
        assert hasattr(orchestrator, "providers")
        assert isinstance(orchestrator.providers, dict)
