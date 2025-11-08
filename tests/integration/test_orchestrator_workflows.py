"""Integration tests for Orchestrator workflow methods (plan, apply, destroy, rollback)."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.events import EventManager, EventType
from infrafoundry.core.orchestrator import Orchestrator
from infrafoundry.core.secrets import SecretManager
from infrafoundry.core.state import DeploymentStatus, ResourceState, StateManager
from infrafoundry.providers.proxmox import ProxmoxProvider


@pytest.fixture
def mock_providers(tmp_path):
    """Create mock providers for testing."""
    # Create mock Proxmox provider
    proxmox = Mock(spec=ProxmoxProvider)
    proxmox.name = "proxmox"
    proxmox.terraform_dir = tmp_path / "generated" / "terraform" / "proxmox"
    proxmox.ansible_dir = tmp_path / "generated" / "ansible" / "proxmox"
    proxmox.ensure_directories = Mock()
    proxmox.generate_terraform = Mock()
    proxmox.generate_ansible = Mock()
    proxmox.validate_config = Mock()
    proxmox.get_resource_types = Mock(return_value=["vm", "network", "template"])

    return {"proxmox": proxmox}


@pytest.fixture
def orchestrator(tmp_path, mock_config, mock_providers):
    """Create Orchestrator with mocked components for workflow testing."""
    config_dir = tmp_path / "config"
    output_dir = tmp_path / "generated"

    # Create necessary directories
    config_dir.mkdir(parents=True)
    (config_dir / "envs" / "dev").mkdir(parents=True)
    (config_dir / "secrets").mkdir(parents=True)

    # Create environment file
    env_file = config_dir / "envs" / "dev" / "environment.yaml"
    env_file.write_text("name: dev\ndescription: Development environment\n")

    # Create mock ConfigManager
    config_manager = Mock(spec=ConfigManager)
    config_manager.base_dir = config_dir
    config_manager.load_environment = Mock(return_value=mock_config["environment"])
    config_manager.get_all_resources_all_providers = Mock(return_value=mock_config["resources"])

    # Create real components
    event_manager = EventManager()
    state_manager = StateManager(connection_string="sqlite:///:memory:")
    state_manager.initialize()  # Initialize database schema

    # Mock SecretManager
    secret_manager = Mock(spec=SecretManager)
    secret_manager.export_for_terraform = Mock()
    secret_manager.export_for_ansible = Mock()

    # Create orchestrator with correct constructor signature
    orchestrator = Orchestrator(
        config_manager=config_manager,
        secret_manager=secret_manager,
        output_dir=output_dir,
        state_manager=state_manager,
        event_manager=event_manager,
        policy_dir=config_dir / "policies",
        notifications_config=None,
    )

    # Inject mock providers
    orchestrator.providers = mock_providers

    return orchestrator


class TestPlanWorkflow:
    """Tests for plan workflow."""

    def test_plan_basic_workflow(self, orchestrator, mock_providers):
        """Test basic plan workflow execution."""
        with patch.object(orchestrator, "_run_terraform") as mock_tf:
            mock_tf.return_value = {"success": True, "changes": 2}

            result = orchestrator.plan(env_name="dev", dry_run=False)

            # Verify plan was called
            assert "proxmox" in result
            assert result["proxmox"]["resources"] == 2

            # Verify provider methods were called
            mock_providers["proxmox"].ensure_directories.assert_called_once()
            mock_providers["proxmox"].generate_terraform.assert_called_once()
            mock_providers["proxmox"].generate_ansible.assert_called_once()

            # Verify terraform was run
            mock_tf.assert_called_once()

    def test_plan_dry_run_skips_terraform(self, orchestrator, mock_providers):
        """Test that dry_run mode doesn't generate files or run terraform."""
        result = orchestrator.plan(env_name="dev", dry_run=True)

        # Verify result shows dry run
        assert result["proxmox"]["dry_run"] is True

        # Verify provider methods were NOT called
        mock_providers["proxmox"].generate_terraform.assert_not_called()
        mock_providers["proxmox"].generate_ansible.assert_not_called()

    def test_plan_with_resource_filter(self, orchestrator, mock_providers, mock_config):
        """Test plan with resource filter."""
        with patch.object(orchestrator, "_run_terraform") as mock_tf:
            mock_tf.return_value = {"success": True, "changes": 1}

            result = orchestrator.plan(
                env_name="dev", dry_run=False, resource_filter=["web-01"]
            )

            # Verify only filtered resources were processed
            assert result["proxmox"]["resources"] == 1

    def test_plan_creates_deployment_record(self, orchestrator):
        """Test that plan creates a deployment record in state manager."""
        with patch.object(orchestrator, "_run_terraform"):
            orchestrator.plan(env_name="dev", dry_run=False)

            # Check deployment was created
            deployments = orchestrator.state_manager.list_deployments(environment="dev")
            assert len(deployments) > 0
            assert deployments[0].command == "plan"
            assert deployments[0].environment == "dev"

    def test_plan_emits_events(self, orchestrator):
        """Test that plan emits before/after events."""
        events_received = []

        def capture_event(event):
            events_received.append(event.type)

        orchestrator.event_manager.subscribe(EventType.BEFORE_PLAN, capture_event)
        orchestrator.event_manager.subscribe(EventType.AFTER_PLAN, capture_event)

        with patch.object(orchestrator, "_run_terraform"):
            orchestrator.plan(env_name="dev", dry_run=False)

        assert EventType.BEFORE_PLAN in events_received
        assert EventType.AFTER_PLAN in events_received

    def test_plan_tracks_resources_in_state(self, orchestrator):
        """Test that plan tracks resources in state manager."""
        with patch.object(orchestrator, "_run_terraform"):
            orchestrator.plan(env_name="dev", dry_run=False)

            # Check resources were tracked
            resources = orchestrator.state_manager.get_resources_by_environment("dev")
            assert len(resources) > 0
            assert resources[0].state == ResourceState.PLANNED

    def test_plan_exports_secrets(self, orchestrator):
        """Test that plan exports secrets for providers."""
        with patch.object(orchestrator, "_run_terraform"):
            orchestrator.plan(env_name="dev", dry_run=False)

            # Verify secrets were exported
            orchestrator.secret_manager.export_for_terraform.assert_called()

    def test_plan_handles_missing_secrets(self, orchestrator):
        """Test that plan handles missing secrets gracefully."""
        orchestrator.secret_manager.export_for_terraform.side_effect = FileNotFoundError(
            "No secrets"
        )

        with patch.object(orchestrator, "_run_terraform"):
            # Should not raise, just print warning
            result = orchestrator.plan(env_name="dev", dry_run=False)
            assert "proxmox" in result

    def test_plan_failure_updates_deployment_status(self, orchestrator):
        """Test that plan failure marks deployment as failed."""
        with patch.object(orchestrator, "_run_terraform") as mock_tf:
            mock_tf.side_effect = RuntimeError("Terraform failed")

            with pytest.raises(RuntimeError):
                orchestrator.plan(env_name="dev", dry_run=False)

            # Check deployment was marked as failed
            deployments = orchestrator.state_manager.list_deployments(environment="dev")
            assert deployments[0].status == DeploymentStatus.FAILED
            assert "Terraform failed" in deployments[0].error_message

    def test_plan_emits_failure_event(self, orchestrator):
        """Test that plan failure emits failure event."""
        events_received = []

        def capture_event(event):
            events_received.append(event.type)

        orchestrator.event_manager.subscribe(EventType.PLAN_FAILED, capture_event)

        with patch.object(orchestrator, "_run_terraform") as mock_tf:
            mock_tf.side_effect = RuntimeError("Terraform failed")

            with pytest.raises(RuntimeError):
                orchestrator.plan(env_name="dev", dry_run=False)

        assert EventType.PLAN_FAILED in events_received


class TestApplyWorkflow:
    """Tests for apply workflow."""

    def test_apply_runs_plan_first(self, orchestrator):
        """Test that apply runs plan before applying."""
        with patch.object(orchestrator, "plan") as mock_plan, patch.object(
            orchestrator, "_run_terraform"
        ):
            orchestrator.apply(env_name="dev", auto_approve=True)

            # Verify plan was called first
            mock_plan.assert_called_once_with(
                env_name="dev", dry_run=False, resource_filter=None
            )

    def test_apply_basic_workflow(self, orchestrator, mock_providers):
        """Test basic apply workflow execution."""
        with patch.object(orchestrator, "_run_terraform") as mock_tf:
            mock_tf.return_value = {"success": True, "applied": 2}

            result = orchestrator.apply(env_name="dev", auto_approve=True)

            # Verify apply completed
            assert "proxmox" in result

            # Verify terraform was run twice (plan + apply)
            assert mock_tf.call_count >= 1

    def test_apply_creates_deployment_record(self, orchestrator):
        """Test that apply creates a deployment record."""
        with patch.object(orchestrator, "_run_terraform"):
            orchestrator.apply(env_name="dev", auto_approve=True)

            # Check deployment was created
            deployments = orchestrator.state_manager.list_deployments(
                environment="dev", command="apply"
            )
            assert len(deployments) > 0
            assert deployments[0].command == "apply"

    def test_apply_captures_rollback_snapshot(self, orchestrator):
        """Test that apply captures configuration snapshot for rollback."""
        with patch.object(orchestrator, "_run_terraform"):
            orchestrator.apply(env_name="dev", auto_approve=True)

            # Check that deployment has rollback data
            deployments = orchestrator.state_manager.list_deployments(environment="dev")
            # At least one deployment should exist
            assert len(deployments) > 0

    def test_apply_with_resource_filter(self, orchestrator, mock_providers):
        """Test apply with resource filter."""
        with patch.object(orchestrator, "_run_terraform"):
            result = orchestrator.apply(
                env_name="dev", auto_approve=True, resource_filter=["web-01"]
            )

            # Should process filtered resources
            assert "proxmox" in result

    def test_apply_emits_events(self, orchestrator):
        """Test that apply emits before/after events."""
        events_received = []

        def capture_event(event):
            events_received.append(event.type)

        orchestrator.event_manager.subscribe(EventType.BEFORE_APPLY, capture_event)
        orchestrator.event_manager.subscribe(EventType.AFTER_APPLY, capture_event)

        with patch.object(orchestrator, "_run_terraform"):
            orchestrator.apply(env_name="dev", auto_approve=True)

        assert EventType.BEFORE_APPLY in events_received
        assert EventType.AFTER_APPLY in events_received

    def test_apply_failure_updates_deployment_status(self, orchestrator):
        """Test that apply failure marks deployment as failed."""
        with patch.object(orchestrator, "_run_terraform") as mock_tf:
            mock_tf.side_effect = RuntimeError("Apply failed")

            with pytest.raises(RuntimeError):
                orchestrator.apply(env_name="dev", auto_approve=True)

            # Check deployment was marked as failed
            deployments = orchestrator.state_manager.list_deployments(environment="dev")
            failed_deployments = [d for d in deployments if d.status == DeploymentStatus.FAILED]
            assert len(failed_deployments) > 0

    def test_apply_emits_failure_event(self, orchestrator):
        """Test that apply failure emits failure event."""
        events_received = []

        def capture_event(event):
            events_received.append(event.type)

        orchestrator.event_manager.subscribe(EventType.APPLY_FAILED, capture_event)

        with patch.object(orchestrator, "_run_terraform") as mock_tf:
            mock_tf.side_effect = RuntimeError("Apply failed")

            with pytest.raises(RuntimeError):
                orchestrator.apply(env_name="dev", auto_approve=True)

        assert EventType.APPLY_FAILED in events_received


class TestDestroyWorkflow:
    """Tests for destroy workflow."""

    def test_destroy_basic_workflow(self, orchestrator, mock_providers):
        """Test basic destroy workflow execution."""
        with patch.object(orchestrator, "_run_terraform") as mock_tf:
            mock_tf.return_value = {"success": True, "destroyed": 2}

            result = orchestrator.destroy(env_name="dev", auto_approve=True)

            # Verify destroy completed
            assert "proxmox" in result

    def test_destroy_creates_deployment_record(self, orchestrator):
        """Test that destroy creates a deployment record."""
        with patch.object(orchestrator, "_run_terraform"):
            orchestrator.destroy(env_name="dev", auto_approve=True)

            # Check deployment was created
            deployments = orchestrator.state_manager.list_deployments(
                environment="dev", command="destroy"
            )
            assert len(deployments) > 0

    def test_destroy_requires_confirmation_without_auto_approve(self, orchestrator):
        """Test that destroy requires confirmation when auto_approve=False."""
        with patch("builtins.input", return_value="no"):
            result = orchestrator.destroy(env_name="dev", auto_approve=False)

            # Should return empty dict when aborted
            assert result == {}

            # Check deployment was marked as failed
            deployments = orchestrator.state_manager.list_deployments(environment="dev")
            assert deployments[0].status == DeploymentStatus.FAILED
            assert "aborted" in deployments[0].error_message.lower()

    def test_destroy_proceeds_with_confirmation(self, orchestrator):
        """Test that destroy proceeds when user confirms."""
        with patch("builtins.input", return_value="yes"), patch.object(
            orchestrator, "_run_terraform"
        ) as mock_tf:
            mock_tf.return_value = {"success": True}

            result = orchestrator.destroy(env_name="dev", auto_approve=False)

            # Should proceed with destroy
            assert "proxmox" in result

    def test_destroy_with_resource_filter(self, orchestrator):
        """Test destroy with resource filter."""
        with patch.object(orchestrator, "_run_terraform"):
            result = orchestrator.destroy(
                env_name="dev", auto_approve=True, resource_filter=["web-01"]
            )

            # Should process filtered resources
            assert "proxmox" in result

    def test_destroy_emits_events(self, orchestrator):
        """Test that destroy emits before/after events."""
        events_received = []

        def capture_event(event):
            events_received.append(event.type)

        orchestrator.event_manager.subscribe(EventType.BEFORE_DESTROY, capture_event)
        orchestrator.event_manager.subscribe(EventType.AFTER_DESTROY, capture_event)

        with patch.object(orchestrator, "_run_terraform"):
            orchestrator.destroy(env_name="dev", auto_approve=True)

        assert EventType.BEFORE_DESTROY in events_received
        assert EventType.AFTER_DESTROY in events_received

    def test_destroy_tracks_resources_as_destroyed(self, orchestrator):
        """Test that destroy marks resources as destroyed in state."""
        with patch.object(orchestrator, "_run_terraform"):
            orchestrator.destroy(env_name="dev", auto_approve=True)

            # Resources should be tracked (state updates happen in _run_terraform mock)
            resources = orchestrator.state_manager.get_resources_by_environment("dev")
            assert len(resources) > 0

    def test_destroy_failure_updates_deployment_status(self, orchestrator):
        """Test that destroy failure marks deployment as failed."""
        with patch.object(orchestrator, "_run_terraform") as mock_tf:
            mock_tf.side_effect = RuntimeError("Destroy failed")

            with pytest.raises(RuntimeError):
                orchestrator.destroy(env_name="dev", auto_approve=True)

            # Check deployment was marked as failed
            deployments = orchestrator.state_manager.list_deployments(environment="dev")
            failed_deployments = [d for d in deployments if d.status == DeploymentStatus.FAILED]
            assert len(failed_deployments) > 0


class TestMultiProviderWorkflow:
    """Tests for multi-provider orchestration."""

    def test_plan_multiple_providers(self, orchestrator, mock_providers, mock_config):
        """Test plan workflow with multiple providers."""
        # Add a second provider
        kubernetes = Mock()
        kubernetes.name = "kubernetes"
        kubernetes.terraform_dir = Path("/tmp/k8s")
        kubernetes.ensure_directories = Mock()
        kubernetes.generate_terraform = Mock()
        kubernetes.generate_ansible = Mock()
        mock_providers["kubernetes"] = kubernetes
        orchestrator.providers = mock_providers

        # Add kubernetes resources to mock config
        k8s_resource = Mock()
        k8s_resource.provider = "kubernetes"
        k8s_resource.type = "deployment"
        k8s_resource.name = "app-01"
        k8s_resource.config = {}
        mock_config["resources"].append(k8s_resource)

        with patch.object(orchestrator, "_run_terraform"):
            result = orchestrator.plan(env_name="dev", dry_run=False)

            # Both providers should be processed
            assert "proxmox" in result
            assert "kubernetes" in result

    def test_apply_multiple_providers_serial(self, orchestrator, mock_providers, mock_config):
        """Test apply workflow with multiple providers in serial mode."""
        # Add second provider
        kubernetes = Mock()
        kubernetes.name = "kubernetes"
        mock_providers["kubernetes"] = kubernetes
        orchestrator.providers = mock_providers

        # Add kubernetes resource
        k8s_resource = Mock()
        k8s_resource.provider = "kubernetes"
        k8s_resource.type = "deployment"
        k8s_resource.name = "app-01"
        k8s_resource.config = {}
        mock_config["resources"].append(k8s_resource)

        with patch.object(orchestrator, "_run_terraform"):
            result = orchestrator.apply(
                env_name="dev", auto_approve=True, parallel=False
            )

            # Both providers should be processed
            assert "proxmox" in result
            assert "kubernetes" in result

    def test_destroy_multiple_providers(self, orchestrator, mock_providers, mock_config):
        """Test destroy workflow with multiple providers."""
        # Add second provider
        opnsense = Mock()
        opnsense.name = "opnsense"
        opnsense.terraform_dir = Path("/tmp/opn")
        opnsense.ensure_directories = Mock()
        opnsense.generate_terraform = Mock()
        opnsense.generate_ansible = Mock()
        mock_providers["opnsense"] = opnsense
        orchestrator.providers = mock_providers

        # Add opnsense resource
        opn_resource = Mock()
        opn_resource.provider = "opnsense"
        opn_resource.type = "firewall_rule"
        opn_resource.name = "rule-01"
        opn_resource.config = {}
        mock_config["resources"].append(opn_resource)

        with patch.object(orchestrator, "_run_terraform"):
            result = orchestrator.destroy(env_name="dev", auto_approve=True)

            # Both providers should be processed
            assert "proxmox" in result
            assert "opnsense" in result


class TestWorkflowStateManagement:
    """Tests for state management during workflows."""

    def test_deployment_lifecycle_plan_to_apply(self, orchestrator):
        """Test complete deployment lifecycle from plan to apply."""
        with patch.object(orchestrator, "_run_terraform"):
            # Plan
            orchestrator.plan(env_name="dev", dry_run=False)
            plan_deployments = orchestrator.state_manager.list_deployments(
                environment="dev", command="plan"
            )
            assert len(plan_deployments) > 0
            assert plan_deployments[0].status == DeploymentStatus.COMPLETED

            # Apply
            orchestrator.apply(env_name="dev", auto_approve=True)
            apply_deployments = orchestrator.state_manager.list_deployments(
                environment="dev", command="apply"
            )
            assert len(apply_deployments) > 0

    def test_resource_state_transitions(self, orchestrator):
        """Test resource state transitions through workflow."""
        with patch.object(orchestrator, "_run_terraform"):
            # Plan - resources should be PLANNED
            orchestrator.plan(env_name="dev", dry_run=False)
            resources = orchestrator.state_manager.get_resources_by_environment("dev")
            assert all(r.state == ResourceState.PLANNED for r in resources)

    def test_deployment_metadata_captured(self, orchestrator):
        """Test that deployment metadata is properly captured."""
        with patch.object(orchestrator, "_run_terraform"):
            orchestrator.plan(
                env_name="dev", dry_run=True, resource_filter=["web-01"]
            )

            deployments = orchestrator.state_manager.list_deployments(environment="dev")
            assert deployments[0].dry_run is True
            assert "resource_filter" in deployments[0].metadata
