"""Unit tests for DriftDetector."""

from unittest.mock import MagicMock

import pytest

from infrafoundry.core.base_manager import BaseManager
from infrafoundry.core.drift_detector import DriftDetector
from infrafoundry.core.events import EventManager


@pytest.fixture
def mock_config_manager():
    """Create a mock config manager."""
    return MagicMock()


@pytest.fixture
def mock_runner_registry():
    """Create a mock runner registry."""
    return MagicMock()


@pytest.fixture
def mock_event_manager():
    """Create a mock event manager."""
    return MagicMock(spec=EventManager)


@pytest.fixture
def mock_providers():
    """Create a mock providers dict."""
    return {}


@pytest.fixture
def drift_detector(mock_config_manager, mock_runner_registry, mock_event_manager, mock_providers):
    """Create a DriftDetector instance for testing."""
    return DriftDetector(
        config_manager=mock_config_manager,
        runner_registry=mock_runner_registry,
        event_manager=mock_event_manager,
        providers=mock_providers,
    )


@pytest.mark.unit
class TestDriftDetector:
    """Tests for DriftDetector."""

    def test_inherits_from_base_manager(self, drift_detector):
        """Test that DriftDetector inherits from BaseManager."""
        assert isinstance(drift_detector, BaseManager)
        # Should have BaseManager methods
        assert hasattr(drift_detector, "_log_info")
        assert hasattr(drift_detector, "_log_warning")
        assert hasattr(drift_detector, "_log_error")
        assert hasattr(drift_detector, "_log_debug")
        assert hasattr(drift_detector, "cleanup")

    def test_cleanup_method(self, drift_detector):
        """Test that cleanup method works."""
        # cleanup() should not raise any exceptions
        drift_detector.cleanup()

    def test_context_manager(
        self, mock_config_manager, mock_runner_registry, mock_event_manager, mock_providers
    ):
        """Test that DriftDetector can be used as context manager."""
        with DriftDetector(
            config_manager=mock_config_manager,
            runner_registry=mock_runner_registry,
            event_manager=mock_event_manager,
            providers=mock_providers,
        ) as detector:
            assert isinstance(detector, DriftDetector)
        # Exiting context should call cleanup without error

    def test_init_stores_dependencies(
        self, mock_config_manager, mock_runner_registry, mock_event_manager, mock_providers
    ):
        """Test that __init__ properly stores dependencies."""
        detector = DriftDetector(
            config_manager=mock_config_manager,
            runner_registry=mock_runner_registry,
            event_manager=mock_event_manager,
            providers=mock_providers,
        )

        assert detector.config_manager is mock_config_manager
        assert detector.runner_registry is mock_runner_registry
        assert detector.event_manager is mock_event_manager
        assert detector.providers is mock_providers

    def test_detect_emits_started_event(
        self, mock_config_manager, mock_runner_registry, mock_event_manager, mock_providers
    ):
        """Test that detect emits DRIFT_CHECK_STARTED event."""
        # Set up mocks
        mock_runner = MagicMock()
        mock_runner_registry.create_runner.return_value = mock_runner
        mock_config_manager.get_all_resources_all_providers.return_value = []

        detector = DriftDetector(
            config_manager=mock_config_manager,
            runner_registry=mock_runner_registry,
            event_manager=mock_event_manager,
            providers=mock_providers,
        )

        detector.detect("test-env")

        # Verify DRIFT_CHECK_STARTED was emitted
        calls = mock_event_manager.emit_event.call_args_list
        assert len(calls) >= 1
        first_call = calls[0]
        assert first_call[0][1] == "test-env"  # environment name

    def test_detect_returns_empty_dict_when_no_providers(
        self, mock_config_manager, mock_runner_registry, mock_event_manager, mock_providers
    ):
        """Test that detect returns empty dict when no providers have resources."""
        # Set up mocks
        mock_runner = MagicMock()
        mock_runner_registry.create_runner.return_value = mock_runner
        mock_config_manager.get_all_resources_all_providers.return_value = []

        detector = DriftDetector(
            config_manager=mock_config_manager,
            runner_registry=mock_runner_registry,
            event_manager=mock_event_manager,
            providers=mock_providers,
        )

        results = detector.detect("test-env")

        assert results == {}
