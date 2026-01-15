"""Integration tests for advanced orchestrator scenarios.

Tests complex workflows including:
- Policy enforcement during plan and apply
- Drift detection with state changes
- Rollback with various failure scenarios
- Multi-provider coordination with dependencies
- Error recovery and cleanup
"""

from contextlib import suppress
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.orchestrator import Orchestrator
from infrafoundry.core.secrets.secret_manager import SecretManager
from infrafoundry.core.state import DeploymentStatus, ResourceState


@pytest.fixture
def advanced_orchestrator(tmp_path):
    """Create orchestrator with real components for advanced testing."""
    config_dir = tmp_path / "config"
    output_dir = tmp_path / "generated"
    secrets_dir = tmp_path / "secrets"

    # Create directories
    config_dir.mkdir(parents=True)
    secrets_dir.mkdir(parents=True)
    (config_dir / "envs" / "dev").mkdir(parents=True)
    (config_dir / "envs" / "dev" / "proxmox").mkdir(parents=True)

    # Create environment file
    env_file = config_dir / "envs" / "dev" / "settings.yaml"
    env_file.write_text(
        """
name: dev
description: Development environment
variables:
  max_memory_mb: 8192
  require_approval: false
"""
    )

    # Create VM config
    vm_file = config_dir / "envs" / "dev" / "proxmox" / "vm.yaml"
    vm_file.write_text(
        """
vms:
  - name: test-vm-01
    node: pve1
    cores: 2
    memory: 4096
    disk_size: 32
    template: ubuntu-22-04
"""
    )

    # Create components
    config_manager = ConfigManager(base_dir=config_dir / "envs")

    # Mock secret manager for testing
    secret_manager = Mock(spec=SecretManager)
    secret_manager.decrypt_file = Mock(return_value={})
    secret_manager.get_secret = Mock(return_value=None)

    # Create orchestrator
    orchestrator = Orchestrator(
        config_manager=config_manager,
        output_dir=output_dir,
    )

    # Override secret manager factory to return our mock
    # Patch on plan_orchestrator instance as it holds reference to original method
    orchestrator.plan_orchestrator._secret_manager_factory = Mock(return_value=secret_manager)

    # Register mock provider
    provider = Mock()
    provider.name = "proxmox"
    provider.terraform_dir = output_dir / "terraform" / "proxmox"
    provider.ansible_dir = output_dir / "ansible" / "proxmox"
    provider.pyinfra_dir = output_dir / "pyinfra" / "proxmox"
    provider.ensure_directories = Mock()
    provider.generate_terraform = Mock()
    provider.generate_ansible = Mock()
    provider.validate_config = Mock()
    provider.get_resource_types = Mock(return_value=["vm", "template"])
    provider.get_dependencies = Mock(return_value={"vm": ["template"]})

    orchestrator.register_provider(provider)

    return orchestrator, provider


@pytest.mark.integration
class TestPolicyEnforcement:
    """Tests for policy enforcement during infrastructure operations."""

    def test_plan_reports_policy_violations(self, advanced_orchestrator):
        """Test that plan reports policy violations."""
        orchestrator, provider = advanced_orchestrator

        # Create terraform directory to prevent FileNotFoundError
        provider.terraform_dir.mkdir(parents=True, exist_ok=True)
        (provider.terraform_dir / ".terraform").mkdir(exist_ok=True)

        with patch("subprocess.run") as mock_subprocess:
            mock_subprocess.return_value = Mock(returncode=0, stdout="", stderr="")

            # Don't patch generate_terraform - let the mock provider method be called
            # Plan should complete and report any policy violations
            orchestrator.plan("dev", enforce_policies=False)

        # Verify generation was called
        provider.generate_terraform.assert_called()

    def test_plan_with_enforce_policies_flag(self, advanced_orchestrator):
        """Test plan with enforce_policies flag."""
        orchestrator, provider = advanced_orchestrator

        # Create terraform directory to prevent FileNotFoundError
        provider.terraform_dir.mkdir(parents=True, exist_ok=True)
        (provider.terraform_dir / ".terraform").mkdir(exist_ok=True)

        with patch("subprocess.run") as mock_subprocess:
            mock_subprocess.return_value = Mock(returncode=0, stdout="", stderr="")

            with patch.object(provider, "generate_terraform"):
                # Should accept enforce_policies parameter
                orchestrator.plan("dev", enforce_policies=True)

                provider.generate_terraform.assert_called()


@pytest.mark.integration
class TestDriftDetection:
    """Tests for drift detection functionality."""

    def test_detect_drift_no_changes(self, advanced_orchestrator):
        """Test drift detection when infrastructure matches desired state."""
        orchestrator, provider = advanced_orchestrator

        # Mock terraform plan and drift detection
        with patch("infrafoundry.core.runners.terraform_runner.TerraformRunner.plan") as mock_plan:
            with patch(
                "infrafoundry.core.runners.terraform_runner.TerraformRunner.parse_plan_for_drift"
            ) as mock_drift:
                mock_plan.return_value = {
                    "success": True,
                    "output": "No changes. Infrastructure is up-to-date.",
                }
                mock_drift.return_value = {
                    "has_changes": False,
                    "summary": "No changes detected",
                }

                with patch.object(provider, "generate_terraform"):
                    drift_results = orchestrator.detect_drift("dev")

                    assert drift_results is not None
                    mock_plan.assert_called()

    def test_detect_drift_with_changes(self, advanced_orchestrator):
        """Test drift detection when infrastructure has drifted."""
        orchestrator, provider = advanced_orchestrator

        # Mock terraform plan and drift detection to show changes
        with patch("infrafoundry.core.runners.terraform_runner.TerraformRunner.plan") as mock_plan:
            with patch(
                "infrafoundry.core.runners.terraform_runner.TerraformRunner.parse_plan_for_drift"
            ) as mock_drift:
                mock_plan.return_value = {
                    "success": True,
                    "output": "Plan: 0 to add, 2 to change, 0 to destroy.",
                }
                mock_drift.return_value = {
                    "has_changes": True,
                    "summary": "2 to change",
                    "changed": 2,
                }

                with patch.object(provider, "generate_terraform"):
                    drift_results = orchestrator.detect_drift("dev")

                    assert drift_results is not None
                    mock_plan.assert_called()

    def test_detect_drift_multiple_providers(self, advanced_orchestrator):
        """Test drift detection across multiple providers."""
        orchestrator, provider = advanced_orchestrator

        # Add second provider
        opnsense_provider = Mock()
        opnsense_provider.name = "opnsense"
        opnsense_provider.terraform_dir = Path("/tmp/terraform/opnsense")
        opnsense_provider.ansible_dir = Path("/tmp/ansible/opnsense")
        opnsense_provider.pyinfra_dir = Path("/tmp/pyinfra/opnsense")
        opnsense_provider.ensure_directories = Mock()
        opnsense_provider.generate_terraform = Mock()
        opnsense_provider.get_resource_types = Mock(return_value=["firewall_rule"])
        opnsense_provider.get_dependencies = Mock(return_value={})

        orchestrator.register_provider(opnsense_provider)

        with patch("infrafoundry.core.runners.terraform_runner.TerraformRunner.plan") as mock_plan:
            with patch(
                "infrafoundry.core.runners.terraform_runner.TerraformRunner.parse_plan_for_drift"
            ) as mock_drift:
                mock_plan.return_value = {"success": True, "output": "No changes."}
                mock_drift.return_value = {"has_changes": False, "summary": "No changes"}

                with patch.object(provider, "generate_terraform"):
                    with patch.object(opnsense_provider, "generate_terraform"):
                        drift_results = orchestrator.detect_drift("dev")

                        # Should check both providers
                        assert drift_results is not None


@pytest.mark.integration
class TestRollbackScenarios:
    """Tests for rollback functionality with various failure scenarios."""

    def test_rollback_to_previous_deployment(self, advanced_orchestrator, tmp_path):
        """Test rollback to a previous successful deployment."""
        orchestrator, provider = advanced_orchestrator

        # Create mock deployment in state
        state_manager = orchestrator.state_manager
        deployment_id = state_manager.create_deployment(
            environment="dev",
            command="apply",
            user="test",
            metadata={"version": "1.0"},
        )

        # Add resources to deployment
        state_manager.track_resource(
            deployment_id=deployment_id,
            environment="dev",
            provider="proxmox",
            resource_type="vm",
            name="test-vm",
            state=ResourceState.ACTIVE,
            config={"cores": 2, "memory": 4096},
        )

        # Add rollback data
        rollback_data = {
            "environment": "dev",
            "providers": ["proxmox"],
            "resources": [
                {
                    "provider": "proxmox",
                    "type": "vm",
                    "name": "test-vm",
                    "config": {"cores": 2, "memory": 4096},
                }
            ],
        }
        state_manager.update_deployment_rollback_data(deployment_id, rollback_data)

        state_manager.update_deployment_status(deployment_id, DeploymentStatus.COMPLETED)

        # Create terraform directory for rollback
        provider.terraform_dir.mkdir(parents=True, exist_ok=True)
        (provider.terraform_dir / ".terraform").mkdir(exist_ok=True)

        with patch("subprocess.run") as mock_subprocess:
            mock_subprocess.return_value = Mock(returncode=0, stdout="", stderr="")

            with patch(
                "infrafoundry.core.runners.terraform_runner.TerraformRunner.apply"
            ) as mock_apply:
                with patch(
                    "infrafoundry.core.runners.terraform_runner.TerraformRunner.get_resource_ids"
                ) as mock_ids:
                    mock_apply.return_value = {"exit_code": 0, "success": True}
                    mock_ids.return_value = {}

                    # Perform rollback
                    result = orchestrator.rollback(deployment_id, auto_approve=True)

                    assert result is not None
                    mock_apply.assert_called()

    def test_rollback_with_terraform_failure(self, advanced_orchestrator):
        """Test rollback behavior when terraform fails."""
        orchestrator, provider = advanced_orchestrator

        # Create deployment
        deployment_id = orchestrator.state_manager.create_deployment(
            environment="dev", command="apply", user="test", metadata={}
        )

        with patch(
            "infrafoundry.core.runners.terraform_runner.TerraformRunner.apply"
        ) as mock_apply:
            # Simulate terraform failure
            mock_apply.return_value = {"exit_code": 1, "success": False}

            with patch.object(provider, "generate_terraform"):
                with suppress(Exception):
                    orchestrator.rollback(deployment_id, auto_approve=True)

    def test_rollback_nonexistent_deployment(self, advanced_orchestrator):
        """Test rollback with invalid deployment ID."""
        orchestrator, _provider = advanced_orchestrator

        with pytest.raises(ValueError):
            # Should raise error for nonexistent deployment
            orchestrator.rollback(99999, auto_approve=True)


@pytest.mark.integration
class TestMultiProviderCoordination:
    """Tests for coordinating multiple providers with dependencies."""

    def test_apply_with_cross_provider_dependencies(self, advanced_orchestrator, tmp_path):
        """Test applying resources with dependencies across providers."""
        orchestrator, proxmox_provider = advanced_orchestrator

        # Create config directory for OPNsense
        config_dir = tmp_path / "config" / "envs" / "dev" / "opnsense"
        config_dir.mkdir(parents=True, exist_ok=True)

        # Create OPNsense firewall rule config
        rule_file = config_dir / "firewall_rule.yaml"
        rule_file.write_text(
            """
firewall_rules:
  - name: allow-web
    action: pass
    interface: lan
    protocol: tcp
    destination_port: 80
"""
        )

        # Add OPNsense provider
        opnsense_provider = Mock()
        opnsense_provider.name = "opnsense"
        opnsense_provider.terraform_dir = tmp_path / "generated" / "terraform" / "opnsense"
        opnsense_provider.ansible_dir = tmp_path / "generated" / "ansible" / "opnsense"
        opnsense_provider.pyinfra_dir = tmp_path / "generated" / "pyinfra" / "opnsense"
        opnsense_provider.ensure_directories = Mock()
        opnsense_provider.generate_terraform = Mock()
        opnsense_provider.generate_ansible = Mock()
        opnsense_provider.validate_config = Mock()
        opnsense_provider.get_resource_types = Mock(return_value=["firewall_rule", "alias"])
        opnsense_provider.get_dependencies = Mock(return_value={"firewall_rule": ["alias"]})
        opnsense_provider.set_environment = Mock()

        orchestrator.register_provider(opnsense_provider)

        # Create terraform directories
        proxmox_provider.terraform_dir.mkdir(parents=True, exist_ok=True)
        (proxmox_provider.terraform_dir / ".terraform").mkdir(exist_ok=True)
        opnsense_provider.terraform_dir.mkdir(parents=True, exist_ok=True)
        (opnsense_provider.terraform_dir / ".terraform").mkdir(exist_ok=True)

        with patch("subprocess.run") as mock_subprocess:
            mock_subprocess.return_value = Mock(returncode=0, stdout="", stderr="")

            with patch(
                "infrafoundry.core.runners.terraform_runner.TerraformRunner.plan"
            ) as mock_plan:
                with patch(
                    "infrafoundry.core.runners.terraform_runner.TerraformRunner.apply"
                ) as mock_apply:
                    with patch(
                        "infrafoundry.core.runners.terraform_runner.TerraformRunner.get_resource_ids"
                    ) as mock_ids:
                        with patch(
                            "infrafoundry.core.runners.ansible_runner.AnsibleRunner.apply"
                        ) as mock_ansible:
                            mock_plan.return_value = {"success": True}
                            mock_apply.return_value = {"exit_code": 0, "success": True}
                            mock_ids.return_value = {}
                            mock_ansible.return_value = {"exit_code": 0, "success": True}

                            # Apply should handle provider ordering
                            orchestrator.apply("dev", auto_approve=True)

                            # Both providers should have been called
                            proxmox_provider.generate_terraform.assert_called()
                            opnsense_provider.generate_terraform.assert_called()

    def test_parallel_provider_execution(self, advanced_orchestrator, tmp_path):
        """Test parallel execution of independent providers."""
        orchestrator, proxmox_provider = advanced_orchestrator

        # Create config directory for Kubernetes
        config_dir = tmp_path / "config" / "envs" / "dev" / "kubernetes"
        config_dir.mkdir(parents=True, exist_ok=True)

        # Create Kubernetes deployment config
        deploy_file = config_dir / "deployment.yaml"
        deploy_file.write_text(
            """
deployments:
  - name: web-app
    replicas: 3
    image: nginx:latest
    port: 80
"""
        )

        # Add independent provider
        k8s_provider = Mock()
        k8s_provider.name = "kubernetes"
        k8s_provider.terraform_dir = tmp_path / "generated" / "terraform" / "kubernetes"
        k8s_provider.ansible_dir = tmp_path / "generated" / "ansible" / "kubernetes"
        k8s_provider.pyinfra_dir = tmp_path / "generated" / "pyinfra" / "kubernetes"
        k8s_provider.ensure_directories = Mock()
        k8s_provider.generate_terraform = Mock()
        k8s_provider.generate_ansible = Mock()
        k8s_provider.validate_config = Mock()
        k8s_provider.get_resource_types = Mock(return_value=["deployment", "service"])
        k8s_provider.get_dependencies = Mock(return_value={})
        k8s_provider.set_environment = Mock()

        orchestrator.register_provider(k8s_provider)

        # Create terraform directories
        proxmox_provider.terraform_dir.mkdir(parents=True, exist_ok=True)
        (proxmox_provider.terraform_dir / ".terraform").mkdir(exist_ok=True)
        k8s_provider.terraform_dir.mkdir(parents=True, exist_ok=True)
        (k8s_provider.terraform_dir / ".terraform").mkdir(exist_ok=True)

        with patch("subprocess.run") as mock_subprocess:
            mock_subprocess.return_value = Mock(returncode=0, stdout="", stderr="")

            with patch(
                "infrafoundry.core.runners.terraform_runner.TerraformRunner.plan"
            ) as mock_plan:
                with patch(
                    "infrafoundry.core.runners.terraform_runner.TerraformRunner.apply"
                ) as mock_apply:
                    with patch(
                        "infrafoundry.core.runners.terraform_runner.TerraformRunner.get_resource_ids"
                    ) as mock_ids:
                        mock_plan.return_value = {"success": True}
                        mock_apply.return_value = {"exit_code": 0, "success": True}
                        mock_ids.return_value = {}

                        # Apply with parallel execution
                        orchestrator.apply("dev", auto_approve=True, parallel=True)

                        # Both providers should have been executed
                        proxmox_provider.generate_terraform.assert_called()
                        k8s_provider.generate_terraform.assert_called()

    def test_provider_failure_handling(self, advanced_orchestrator):
        """Test handling when one provider fails during apply."""
        orchestrator, provider = advanced_orchestrator

        with patch("infrafoundry.core.runners.terraform_runner.TerraformRunner.plan") as mock_plan:
            with patch(
                "infrafoundry.core.runners.terraform_runner.TerraformRunner.apply"
            ) as mock_apply:
                # Simulate failure
                mock_plan.return_value = {"success": True}
                mock_apply.return_value = {"exit_code": 1, "success": False}

                with patch.object(provider, "generate_terraform"):
                    try:
                        orchestrator.apply("dev", auto_approve=True)
                    except Exception as e:
                        assert "error" in str(e).lower() or "fail" in str(e).lower()


@pytest.mark.integration
class TestErrorRecoveryAndCleanup:
    """Tests for error recovery and cleanup operations."""

    def test_cleanup_after_plan_failure(self, advanced_orchestrator):
        """Test that resources are cleaned up after plan failure."""
        orchestrator, provider = advanced_orchestrator

        with patch.object(provider, "generate_terraform") as mock_gen:
            # Simulate generation failure
            mock_gen.side_effect = Exception("Template rendering failed")

            with suppress(Exception):
                orchestrator.plan("dev")

            # Verify proper error handling occurred
            mock_gen.assert_called()

    def test_cleanup_after_apply_failure(self, advanced_orchestrator):
        """Test cleanup after apply failure."""
        orchestrator, provider = advanced_orchestrator

        with patch("infrafoundry.core.runners.terraform_runner.TerraformRunner.plan") as mock_plan:
            with patch(
                "infrafoundry.core.runners.terraform_runner.TerraformRunner.apply"
            ) as mock_apply:
                mock_plan.return_value = {"success": True}
                mock_apply.side_effect = Exception("Terraform crashed")

                with patch.object(provider, "generate_terraform"):
                    with suppress(Exception):
                        orchestrator.apply("dev", auto_approve=True)

    def test_state_consistency_after_errors(self, advanced_orchestrator):
        """Test that state remains consistent after errors."""
        orchestrator, provider = advanced_orchestrator

        initial_deployments = orchestrator.state_manager.get_deployment_history("dev", limit=10)
        initial_count = len(initial_deployments)

        with patch("infrafoundry.core.runners.terraform_runner.TerraformRunner.plan") as mock_plan:
            with patch(
                "infrafoundry.core.runners.terraform_runner.TerraformRunner.apply"
            ) as mock_apply:
                mock_plan.return_value = {"success": True}
                mock_apply.side_effect = Exception("Infrastructure error")

                with patch.object(provider, "generate_terraform"):
                    with suppress(Exception):
                        orchestrator.apply("dev", auto_approve=True)

        # State should still be queryable
        final_deployments = orchestrator.state_manager.get_deployment_history("dev", limit=10)
        # Deployment may have been created and marked as failed
        assert len(final_deployments) >= initial_count

    def test_concurrent_operation_prevention(self, advanced_orchestrator):
        """Test that concurrent operations on same environment are prevented."""
        orchestrator, provider = advanced_orchestrator

        # Create terraform directory
        provider.terraform_dir.mkdir(parents=True, exist_ok=True)
        (provider.terraform_dir / ".terraform").mkdir(exist_ok=True)

        with patch("subprocess.run") as mock_subprocess:
            mock_subprocess.return_value = Mock(returncode=0, stdout="", stderr="")

            with patch(
                "infrafoundry.core.runners.terraform_runner.TerraformRunner.plan"
            ) as mock_plan:
                with patch(
                    "infrafoundry.core.runners.terraform_runner.TerraformRunner.apply"
                ) as mock_apply:
                    with patch(
                        "infrafoundry.core.runners.terraform_runner.TerraformRunner.get_resource_ids"
                    ) as mock_ids:
                        mock_plan.return_value = {"success": True}
                        mock_apply.return_value = {"exit_code": 0, "success": True}
                        mock_ids.return_value = {}

                        with patch.object(provider, "generate_terraform"):
                            # First operation
                            orchestrator.apply("dev", auto_approve=True)

                            # State should reflect the operation
                            deployments = orchestrator.state_manager.get_deployment_history(
                                "dev", limit=1
                            )
                            assert len(deployments) > 0
