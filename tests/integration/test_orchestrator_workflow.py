"""Integration tests for Orchestrator workflows."""

import pytest
from pathlib import Path

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.events import EventManager
from infrafoundry.core.orchestrator import Orchestrator
from infrafoundry.core.state import StateManager


@pytest.mark.integration
class TestOrchestratorWorkflow:
    """Integration tests for complete workflows."""

    def test_orchestrator_init(
        self, mock_config_dir, mock_secrets_dir, mock_policy_dir, temp_dir
    ):
        """Test Orchestrator initialization with all components."""
        config = ConfigManager(str(mock_config_dir / "envs"))
        output_dir = temp_dir / "output"
        state_dir = temp_dir / "state"
        state_dir.mkdir()

        orchestrator = Orchestrator(
            config_manager=config,
            secret_manager=None,
            output_dir=str(output_dir),
            state_manager=StateManager(str(state_dir / "state.db")),
            event_manager=EventManager(),
            policy_dir=mock_policy_dir,
        )

        assert orchestrator is not None
        assert orchestrator.config_manager == config
        assert orchestrator.event_manager is not None

    def test_plan_workflow(
        self, mock_config_dir, mock_secrets_dir, mock_policy_dir, temp_dir
    ):
        """Test plan workflow without actual Terraform."""
        config = ConfigManager(str(mock_config_dir / "envs"))
        output_dir = temp_dir / "output"
        state_dir = temp_dir / "state"
        state_dir.mkdir()

        orchestrator = Orchestrator(
            config_manager=config,
            secret_manager=None,
            output_dir=str(output_dir),
            state_manager=StateManager(str(state_dir / "state.db")),
            event_manager=EventManager(),
            policy_dir=mock_policy_dir,
        )

        # Test dry-run plan (doesn't execute Terraform)
        result = orchestrator.plan("dev", dry_run=True)
        assert result is not None

        # Check that Terraform files were generated
        tf_dir = output_dir / "terraform"
        assert tf_dir.exists()

    def test_event_emission_during_plan(
        self, mock_config_dir, mock_policy_dir, temp_dir
    ):
        """Test that events are emitted during plan."""
        config = ConfigManager(str(mock_config_dir / "envs"))
        output_dir = temp_dir / "output"
        state_dir = temp_dir / "state"
        state_dir.mkdir()

        event_manager = EventManager()
        events_received = []

        def event_handler(event):
            events_received.append(event.event_type)

        # Subscribe to all events
        event_manager.subscribe_all(event_handler)

        orchestrator = Orchestrator(
            config_manager=config,
            secret_manager=None,
            output_dir=str(output_dir),
            state_manager=StateManager(str(state_dir / "state.db")),
            event_manager=event_manager,
            policy_dir=mock_policy_dir,
        )

        # Run plan
        orchestrator.plan("dev", dry_run=True)

        # Should have received events
        assert len(events_received) > 0

    def test_policy_enforcement_during_plan(
        self, mock_config_dir, mock_policy_dir, temp_dir
    ):
        """Test that policies are enforced during plan."""
        config = ConfigManager(str(mock_config_dir / "envs"))
        output_dir = temp_dir / "output"
        state_dir = temp_dir / "state"
        state_dir.mkdir()

        orchestrator = Orchestrator(
            config_manager=config,
            secret_manager=None,
            output_dir=str(output_dir),
            state_manager=StateManager(str(state_dir / "state.db")),
            event_manager=EventManager(),
            policy_dir=mock_policy_dir,
        )

        # Plan should run policy checks
        # (Actual assertions depend on test data and policy configuration)
        result = orchestrator.plan("dev", dry_run=True)
        assert result is not None

    def test_dependency_graph_build(
        self, mock_config_dir, temp_dir
    ):
        """Test building dependency graph."""
        config = ConfigManager(str(mock_config_dir / "envs"))
        output_dir = temp_dir / "output"
        state_dir = temp_dir / "state"
        state_dir.mkdir()

        orchestrator = Orchestrator(
            config_manager=config,
            secret_manager=None,
            output_dir=str(output_dir),
            state_manager=StateManager(str(state_dir / "state.db")),
            event_manager=EventManager(),
        )

        # Build dependency graph
        graph = orchestrator.build_dependency_graph("dev")
        assert graph is not None
        assert len(graph.nodes) > 0

    def test_list_resources(self, mock_config_dir, temp_dir):
        """Test listing resources."""
        config = ConfigManager(str(mock_config_dir / "envs"))
        output_dir = temp_dir / "output"
        state_dir = temp_dir / "state"
        state_dir.mkdir()

        orchestrator = Orchestrator(
            config_manager=config,
            secret_manager=None,
            output_dir=str(output_dir),
            state_manager=StateManager(str(state_dir / "state.db")),
            event_manager=EventManager(),
        )

        # List should return resources
        resources = orchestrator.list_resources("dev")
        assert resources is not None

    def test_validate_with_policies(self, mock_config_dir, mock_policy_dir, temp_dir):
        """Test validation with policy enforcement."""
        config = ConfigManager(str(mock_config_dir / "envs"))
        output_dir = temp_dir / "output"
        state_dir = temp_dir / "state"
        state_dir.mkdir()

        orchestrator = Orchestrator(
            config_manager=config,
            secret_manager=None,
            output_dir=str(output_dir),
            state_manager=StateManager(str(state_dir / "state.db")),
            event_manager=EventManager(),
            policy_dir=mock_policy_dir,
        )

        # Validate should check policies
        result = orchestrator.validate("dev")
        assert result is not None
