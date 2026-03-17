"""Unit tests for Orchestrator class."""

import os
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.events import EventManager
from infrafoundry.core.exceptions import ResourceFilterError
from infrafoundry.core.notifications import NotificationManager
from infrafoundry.core.orchestrator import Orchestrator, OrchestratorStrictConfig
from infrafoundry.core.policy import PolicyEngine
from infrafoundry.core.provider import ProviderBase
from infrafoundry.core.state import StateManager


class TestOrchestratorInit:
    """Tests for Orchestrator initialization."""

    def test_init_with_defaults(self, tmp_path):
        """Test initialization with default parameters."""
        config_manager = Mock(spec=ConfigManager)
        config_manager.base_dir = tmp_path

        orchestrator = Orchestrator(
            config_manager=config_manager,
        )

        assert orchestrator.config_manager == config_manager
        assert orchestrator.output_dir == Path.cwd() / "generated"
        assert isinstance(orchestrator.state_manager, StateManager)
        assert isinstance(orchestrator.event_manager, EventManager)
        assert isinstance(orchestrator.policy_engine, PolicyEngine)
        assert isinstance(orchestrator.notification_manager, NotificationManager)
        assert orchestrator.providers == {}

    def test_init_with_custom_output_dir(self, tmp_path):
        """Test initialization with custom output directory."""
        config_manager = Mock(spec=ConfigManager)
        config_manager.base_dir = tmp_path
        output_dir = tmp_path / "custom_output"

        orchestrator = Orchestrator(
            config_manager=config_manager,
            output_dir=output_dir,
        )

        assert orchestrator.output_dir == output_dir
        assert output_dir.exists()

    def test_init_with_custom_managers(self, tmp_path):
        """Test initialization with custom manager instances."""
        config_manager = Mock(spec=ConfigManager)
        config_manager.base_dir = tmp_path
        state_manager = Mock(spec=StateManager)
        state_manager.SessionLocal = Mock()  # Required for AuditLogger initialization
        event_manager = Mock(spec=EventManager)

        orchestrator = Orchestrator(
            config_manager=config_manager,
            state_manager=state_manager,
            event_manager=event_manager,
        )

        assert orchestrator.state_manager == state_manager
        assert orchestrator.event_manager == event_manager

    def test_init_creates_output_directory(self, tmp_path):
        """Test that initialization creates output directory if it doesn't exist."""
        config_manager = Mock(spec=ConfigManager)
        config_manager.base_dir = tmp_path
        output_dir = tmp_path / "nested" / "output" / "dir"

        assert not output_dir.exists()

        Orchestrator(
            config_manager=config_manager,
            output_dir=output_dir,
        )

        assert output_dir.exists()

    def test_init_sets_current_user(self, tmp_path):
        """Test that initialization captures current user from environment."""
        config_manager = Mock(spec=ConfigManager)
        config_manager.base_dir = tmp_path

        with patch.dict(os.environ, {"USER": "testuser"}):
            orchestrator = Orchestrator(
                config_manager=config_manager,
            )
            assert orchestrator._get_current_user() == "testuser"

    def test_init_fallback_user(self, tmp_path):
        """Test user fallback when USER env var not set."""
        config_manager = Mock(spec=ConfigManager)
        config_manager.base_dir = tmp_path

        # Clear USER and USERNAME
        env = os.environ.copy()
        env.pop("USER", None)
        env.pop("USERNAME", None)

        with patch.dict(os.environ, env, clear=True):
            orchestrator = Orchestrator(
                config_manager=config_manager,
            )
            assert orchestrator._get_current_user() == "unknown"


class TestOrchestratorNotifications:
    """Tests for notification setup and handling."""

    def test_setup_notifications_with_channels(self, tmp_path):
        """Test that notifications are set up when channels exist."""
        config_manager = Mock(spec=ConfigManager)
        config_manager.base_dir = tmp_path
        event_manager = Mock(spec=EventManager)

        # Mock notification manager with channels
        notification_manager = Mock(spec=NotificationManager)
        notification_manager.channels = {"slack": Mock()}

        with patch.object(Orchestrator, "_setup_notifications") as mock_setup:
            orchestrator = Orchestrator(
                config_manager=config_manager,
                event_manager=event_manager,
            )
            orchestrator.notification_manager = notification_manager
            orchestrator._setup_notifications()

            mock_setup.assert_called()

    def test_setup_notifications_without_channels(self, tmp_path):
        """Test that notifications are skipped when no channels configured."""
        config_manager = Mock(spec=ConfigManager)
        config_manager.base_dir = tmp_path

        orchestrator = Orchestrator(
            config_manager=config_manager,
        )

        # Should not raise error when no channels
        orchestrator._setup_notifications()


class TestOrchestratorProviderManagement:
    """Tests for provider registration and management."""

    def test_register_provider(self, tmp_path):
        """Test registering a provider."""
        config_manager = Mock(spec=ConfigManager)
        config_manager.base_dir = tmp_path
        orchestrator = Orchestrator(config_manager)

        provider = Mock(spec=ProviderBase)
        provider.name = "test_provider"

        orchestrator.register_provider(provider)

        assert "test_provider" in orchestrator.providers
        assert orchestrator.providers["test_provider"] == provider

    def test_register_multiple_providers(self, tmp_path):
        """Test registering multiple providers."""
        config_manager = Mock(spec=ConfigManager)
        config_manager.base_dir = tmp_path
        orchestrator = Orchestrator(config_manager)

        provider1 = Mock(spec=ProviderBase)
        provider1.name = "proxmox"
        provider2 = Mock(spec=ProviderBase)
        provider2.name = "opnsense"

        orchestrator.register_provider(provider1)
        orchestrator.register_provider(provider2)

        assert len(orchestrator.providers) == 2
        assert orchestrator.providers["proxmox"] == provider1
        assert orchestrator.providers["opnsense"] == provider2

    def test_register_provider_overwrites_existing(self, tmp_path):
        """Test that registering a provider with same name overwrites."""
        config_manager = Mock(spec=ConfigManager)
        config_manager.base_dir = tmp_path
        orchestrator = Orchestrator(config_manager)

        provider1 = Mock(spec=ProviderBase)
        provider1.name = "test"
        provider2 = Mock(spec=ProviderBase)
        provider2.name = "test"

        orchestrator.register_provider(provider1)
        orchestrator.register_provider(provider2)

        assert orchestrator.providers["test"] == provider2

    def test_register_provider_applies_strict_snippet_flag(self, tmp_path):
        """Provider inherits strict snippet config when registered."""
        config_manager = Mock(spec=ConfigManager)
        config_manager.base_dir = tmp_path
        orchestrator = Orchestrator(
            config_manager,
            strict_config=OrchestratorStrictConfig(fail_on_missing_snippets=True),
        )
        provider = Mock()
        provider.name = "proxmox"
        provider.fail_on_missing_snippets = False

        orchestrator.register_provider(provider)

        assert provider.fail_on_missing_snippets is True


class TestOrchestratorValidateResources:
    """Tests for resource validation."""

    def test_validate_resources_all_valid(self, tmp_path):
        """Test validation succeeds when all resources are valid."""
        config_manager = Mock(spec=ConfigManager)
        config_manager.base_dir = tmp_path
        orchestrator = Orchestrator(config_manager)

        # Register provider
        provider = Mock(spec=ProviderBase)
        provider.name = "proxmox"
        provider.get_resource_types.return_value = ["vm", "network"]
        orchestrator.register_provider(provider)

        # Create resources
        resource1 = Mock()
        resource1.provider = "proxmox"
        resource1.type = "vm"
        resource1.name = "test-vm"

        resource2 = Mock()
        resource2.provider = "proxmox"
        resource2.type = "network"
        resource2.name = "test-net"

        # Should not raise
        orchestrator.validate_resources([resource1, resource2])

    def test_validate_resources_provider_not_registered(self, tmp_path):
        """Test validation fails when provider not registered."""
        config_manager = Mock(spec=ConfigManager)
        config_manager.base_dir = tmp_path
        orchestrator = Orchestrator(config_manager)

        resource = Mock()
        resource.provider = "nonexistent"
        resource.type = "vm"
        resource.name = "test-vm"

        with pytest.raises(ValueError, match="Provider 'nonexistent' not registered"):
            orchestrator.validate_resources([resource])

    def test_validate_resources_type_not_supported(self, tmp_path):
        """Test validation fails when resource type not supported."""
        config_manager = Mock(spec=ConfigManager)
        config_manager.base_dir = tmp_path
        orchestrator = Orchestrator(config_manager)

        provider = Mock(spec=ProviderBase)
        provider.name = "proxmox"
        provider.get_resource_types.return_value = ["vm"]
        orchestrator.register_provider(provider)

        resource = Mock()
        resource.provider = "proxmox"
        resource.type = "unsupported_type"
        resource.name = "test-resource"

        with pytest.raises(
            ValueError,
            match="Provider 'proxmox' does not support resource type 'unsupported_type'",
        ):
            orchestrator.validate_resources([resource])

    def test_validate_resources_empty_list(self, tmp_path):
        """Test validation succeeds with empty resource list."""
        config_manager = Mock(spec=ConfigManager)
        config_manager.base_dir = tmp_path
        orchestrator = Orchestrator(config_manager)

        # Should not raise
        orchestrator.validate_resources([])


class TestOrchestratorBuildDependencyGraph:
    """Tests for dependency graph building."""

    def test_build_dependency_graph_basic(self, tmp_path):
        """Test building a basic dependency graph."""
        config_manager = Mock(spec=ConfigManager)
        config_manager.base_dir = tmp_path
        orchestrator = Orchestrator(config_manager)

        # Register provider with dependencies
        provider = Mock(spec=ProviderBase)
        provider.name = "proxmox"
        provider.get_resource_types.return_value = ["template", "vm"]
        provider.get_dependencies.return_value = {"vm": ["template"]}
        orchestrator.register_provider(provider)

        # Mock resources
        template = Mock()
        template.provider = "proxmox"
        template.type = "template"
        template.name = "ubuntu-template"

        vm = Mock()
        vm.provider = "proxmox"
        vm.type = "vm"
        vm.name = "web-server"

        config_manager.get_all_resources_all_providers.return_value = [template, vm]

        graph = orchestrator.build_dependency_graph("dev")

        # Verify graph structure - nodes are keyed by "provider:name"
        assert "proxmox:ubuntu-template" in graph.nodes
        assert "proxmox:web-server" in graph.nodes

    def test_build_dependency_graph_multi_provider(self, tmp_path):
        """Test building dependency graph with multiple providers."""
        config_manager = Mock(spec=ConfigManager)
        config_manager.base_dir = tmp_path
        orchestrator = Orchestrator(config_manager)

        # Register multiple providers
        proxmox = Mock(spec=ProviderBase)
        proxmox.name = "proxmox"
        proxmox.get_resource_types.return_value = ["vm"]
        proxmox.get_dependencies.return_value = {}
        orchestrator.register_provider(proxmox)

        opnsense = Mock(spec=ProviderBase)
        opnsense.name = "opnsense"
        opnsense.get_resource_types.return_value = ["firewall_rule"]
        opnsense.get_dependencies.return_value = {}
        orchestrator.register_provider(opnsense)

        # Mock resources from different providers
        vm = Mock()
        vm.provider = "proxmox"
        vm.type = "vm"
        vm.name = "web-server"

        firewall = Mock()
        firewall.provider = "opnsense"
        firewall.type = "firewall_rule"
        firewall.name = "allow-http"

        config_manager.get_all_resources_all_providers.return_value = [vm, firewall]

        graph = orchestrator.build_dependency_graph("dev")

        # Nodes are keyed by "provider:name"
        assert "proxmox:web-server" in graph.nodes
        assert "opnsense:allow-http" in graph.nodes


class TestOrchestratorStatus:
    """Tests for status reporting."""

    def test_status_no_resources(self, tmp_path, capsys):
        """Test status when no resources exist."""
        config_manager = Mock(spec=ConfigManager)
        config_manager.base_dir = tmp_path
        config_manager.get_all_resources_all_providers.return_value = []

        orchestrator = Orchestrator(config_manager)

        orchestrator.status("dev")

        # Verify config manager was called
        config_manager.get_all_resources_all_providers.assert_called_once_with("dev")

    def test_status_with_resources(self, tmp_path):
        """Test status with resources."""
        config_manager = Mock(spec=ConfigManager)
        config_manager.base_dir = tmp_path

        # Mock resource
        vm = Mock()
        vm.provider = "proxmox"
        vm.type = "vm"
        vm.name = "web-server"

        config_manager.get_all_resources_all_providers.return_value = [vm]

        orchestrator = Orchestrator(config_manager)

        # Register provider with terraform_dir
        provider = Mock(spec=ProviderBase)
        provider.name = "proxmox"
        provider.terraform_dir = Path("/tmp/terraform/proxmox")
        orchestrator.register_provider(provider)

        orchestrator.status("dev")

        config_manager.get_all_resources_all_providers.assert_called_once_with("dev")

    def test_status_with_unregistered_provider(self, tmp_path):
        """Test status with resource from unregistered provider."""
        config_manager = Mock(spec=ConfigManager)
        config_manager.base_dir = tmp_path

        # Mock resource from unregistered provider
        vm = Mock()
        vm.provider = "proxmox"
        vm.type = "vm"
        vm.name = "web-server"

        config_manager.get_all_resources_all_providers.return_value = [vm]

        orchestrator = Orchestrator(config_manager)
        # Don't register the provider

        orchestrator.status("dev")

        # Should still work, just show "Not registered"
        config_manager.get_all_resources_all_providers.assert_called_once_with("dev")


class TestPlanOrchestratorStrictMode:
    """Tests for PlanOrchestrator — secrets are now passed via env vars, not files."""

    pass


class TestIterProviderBatchesResourceFilter:
    """Tests for resource filter validation in _iter_provider_batches."""

    def _make_orchestrator(self, tmp_path):
        """Create a minimal Orchestrator for testing _iter_provider_batches."""
        config_manager = Mock(spec=ConfigManager)
        config_manager.base_dir = tmp_path
        config_manager.load_environment.return_value = None
        config_manager.get_all_resources_all_providers.return_value = []
        return Orchestrator(config_manager)

    def _resource(self, name, provider="proxmox", type_="vm"):
        from infrafoundry.core.provider import ResourceConfig

        return ResourceConfig(name=name, provider=provider, type=type_, config={"id": name})

    def test_no_filter_returns_all_batches(self, tmp_path):
        """No resource filter returns all provider batches."""
        orchestrator = self._make_orchestrator(tmp_path)
        resources_by_provider = {
            "proxmox": [self._resource("vm1"), self._resource("vm2")],
        }

        batches = orchestrator._iter_provider_batches(resources_by_provider, None)

        assert len(batches) == 1
        assert len(batches[0].resources) == 2

    def test_full_match_returns_filtered_batches(self, tmp_path):
        """Filter matching all names returns those resources without error."""
        orchestrator = self._make_orchestrator(tmp_path)
        resources_by_provider = {
            "proxmox": [self._resource("vm1"), self._resource("vm2")],
        }

        batches = orchestrator._iter_provider_batches(resources_by_provider, ["vm1", "vm2"])

        assert len(batches) == 1
        assert {r.name for r in batches[0].resources} == {"vm1", "vm2"}

    def test_zero_matches_raises_resource_filter_error(self, tmp_path):
        """Filter matching zero resources raises ResourceFilterError."""
        orchestrator = self._make_orchestrator(tmp_path)
        resources_by_provider = {
            "proxmox": [self._resource("vm1"), self._resource("vm2")],
        }

        with pytest.raises(ResourceFilterError, match="No resources matched filter"):
            orchestrator._iter_provider_batches(resources_by_provider, ["nonexistent"])

    def test_zero_matches_error_includes_available_names(self, tmp_path):
        """Error message includes unmatched and available resource names."""
        orchestrator = self._make_orchestrator(tmp_path)
        resources_by_provider = {
            "proxmox": [self._resource("vm1"), self._resource("vm2")],
        }

        with pytest.raises(ResourceFilterError, match="nonexistent") as exc_info:
            orchestrator._iter_provider_batches(resources_by_provider, ["nonexistent"])

        error_msg = str(exc_info.value)
        assert "nonexistent" in error_msg
        assert "vm1" in error_msg
        assert "vm2" in error_msg

    def test_partial_match_warns_but_succeeds(self, tmp_path, capsys):
        """Partial filter match warns about unmatched names but returns results."""
        orchestrator = self._make_orchestrator(tmp_path)
        resources_by_provider = {
            "proxmox": [self._resource("vm1"), self._resource("vm2")],
        }

        batches = orchestrator._iter_provider_batches(resources_by_provider, ["vm1", "nonexistent"])

        assert len(batches) == 1
        assert batches[0].resources[0].name == "vm1"

    def test_partial_match_across_providers(self, tmp_path):
        """Partial match works across multiple providers."""
        orchestrator = self._make_orchestrator(tmp_path)
        resources_by_provider = {
            "proxmox": [self._resource("vm1", provider="proxmox")],
            "opnsense": [self._resource("fw1", provider="opnsense", type_="firewall")],
        }

        batches = orchestrator._iter_provider_batches(resources_by_provider, ["vm1", "fw1"])

        assert len(batches) == 2
        all_names = {r.name for b in batches for r in b.resources}
        assert all_names == {"vm1", "fw1"}
