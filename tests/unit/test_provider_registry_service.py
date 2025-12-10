"""Unit tests for ProviderRegistryService."""

from types import SimpleNamespace
from unittest.mock import Mock

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.provider import ProviderBase
from infrafoundry.core.provider_registry_service import ProviderRegistryService
from infrafoundry.core.runners import RunnerRegistry


class TestProviderRegistryService:
    """Tests for ProviderRegistryService."""

    def test_init_with_defaults(self, tmp_path):
        """Test initialization with default parameters."""
        config_manager = Mock(spec=ConfigManager)
        service = ProviderRegistryService(
            base_output_dir=tmp_path,
            config_manager=config_manager,
        )

        assert service.base_output_dir == tmp_path
        assert service.config_manager == config_manager
        assert isinstance(service.runner_registry, RunnerRegistry)
        assert service.providers == {}

    def test_init_with_custom_runner_registry(self, tmp_path):
        """Test initialization with custom runner registry factory."""
        config_manager = Mock(spec=ConfigManager)
        mock_registry = Mock(spec=RunnerRegistry)
        factory = Mock(return_value=mock_registry)

        service = ProviderRegistryService(
            base_output_dir=tmp_path,
            config_manager=config_manager,
            runner_registry_factory=factory,
        )

        assert service.runner_registry == mock_registry
        factory.assert_called_once()

    def test_register_provider(self, tmp_path):
        """Test registering a provider."""
        config_manager = Mock(spec=ConfigManager)
        service = ProviderRegistryService(
            base_output_dir=tmp_path,
            config_manager=config_manager,
        )

        provider = Mock(spec=ProviderBase)
        provider.name = "test_provider"

        service.register_provider(provider)

        assert "test_provider" in service.providers
        assert service.providers["test_provider"] == provider

    def test_get_runner_priorities_with_config(self, tmp_path):
        """Test fetching runner priorities when config exists."""
        config_manager = Mock(spec=ConfigManager)
        env_config = SimpleNamespace(runner_priorities={"terraform": 10, "ansible": 20})
        config_manager.load_environment.return_value = env_config

        service = ProviderRegistryService(
            base_output_dir=tmp_path,
            config_manager=config_manager,
        )

        priorities = service.get_runner_priorities("dev")

        assert priorities == {"terraform": 10, "ansible": 20}
        config_manager.load_environment.assert_called_once_with("dev")

    def test_get_runner_priorities_no_config(self, tmp_path):
        """Test fetching runner priorities when config is missing."""
        config_manager = Mock(spec=ConfigManager)
        config_manager.load_environment.return_value = None

        service = ProviderRegistryService(
            base_output_dir=tmp_path,
            config_manager=config_manager,
        )

        priorities = service.get_runner_priorities("dev")

        assert priorities == {}
        config_manager.load_environment.assert_called_once_with("dev")

    def test_register_default_runners(self, tmp_path):
        """Test that default runners are registered on init."""
        config_manager = Mock(spec=ConfigManager)
        mock_registry = Mock(spec=RunnerRegistry)
        factory = Mock(return_value=mock_registry)

        ProviderRegistryService(
            base_output_dir=tmp_path,
            config_manager=config_manager,
            runner_registry_factory=factory,
        )

        # Verify registration calls
        # We expect register to be called for TerraformRunner, AnsibleRunner, PyInfraRunner
        assert mock_registry.register.call_count == 3
