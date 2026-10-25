"""Unit tests for DriftDetector."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.base_manager import BaseManager
from infrafoundry.core.drift_detector import DriftDetector
from infrafoundry.core.events import EventManager, EventType
from infrafoundry.core.runners.terraform_runner import TerraformRunner


@pytest.fixture
def mock_config_manager() -> MagicMock:
    """Create a mock config manager."""
    return MagicMock()


@pytest.fixture
def mock_runner_registry() -> MagicMock:
    """Create a mock runner registry."""
    return MagicMock()


@pytest.fixture
def mock_event_manager() -> MagicMock:
    """Create a mock event manager."""
    return MagicMock(spec=EventManager)


@pytest.fixture
def mock_providers() -> dict[str, Any]:
    """Create a mock providers dict."""
    return {}


@pytest.fixture
def drift_detector(
    mock_config_manager: MagicMock,
    mock_runner_registry: MagicMock,
    mock_event_manager: MagicMock,
    mock_providers: dict[str, Any],
) -> DriftDetector:
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

    def test_inherits_from_base_manager(self, drift_detector: DriftDetector) -> None:
        """Test that DriftDetector inherits from BaseManager."""
        assert isinstance(drift_detector, BaseManager)
        # Should have BaseManager methods
        assert hasattr(drift_detector, "_log_info")
        assert hasattr(drift_detector, "_log_warning")
        assert hasattr(drift_detector, "_log_error")
        assert hasattr(drift_detector, "_log_debug")
        assert hasattr(drift_detector, "cleanup")

    def test_cleanup_method(self, drift_detector: DriftDetector) -> None:
        """Test that cleanup method works."""
        # cleanup() should not raise any exceptions
        drift_detector.cleanup()

    def test_context_manager(
        self,
        mock_config_manager: MagicMock,
        mock_runner_registry: MagicMock,
        mock_event_manager: MagicMock,
        mock_providers: dict[str, Any],
    ) -> None:
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
        self,
        mock_config_manager: MagicMock,
        mock_runner_registry: MagicMock,
        mock_event_manager: MagicMock,
        mock_providers: dict[str, Any],
    ) -> None:
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
        self,
        mock_config_manager: MagicMock,
        mock_runner_registry: MagicMock,
        mock_event_manager: MagicMock,
        mock_providers: dict[str, Any],
    ) -> None:
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
        self,
        mock_config_manager: MagicMock,
        mock_runner_registry: MagicMock,
        mock_event_manager: MagicMock,
        mock_providers: dict[str, Any],
    ) -> None:
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

    def test_detect_uses_configured_iac_tool(
        self,
        mock_config_manager: MagicMock,
        mock_runner_registry: MagicMock,
        mock_event_manager: MagicMock,
        mock_providers: dict[str, Any],
    ) -> None:
        """Test that detect resolves the IaC tool from environment config."""
        from infrafoundry.core.config.models import EnvironmentConfig, IaCTool

        # Configure environment with opentofu
        env_config = EnvironmentConfig(name="test-env", iac_tool=IaCTool.OPENTOFU)
        mock_config_manager.load_environment.return_value = env_config

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

        # Should create runner with "opentofu", not "terraform"
        mock_runner_registry.create_runner.assert_called_once_with("opentofu")

    def test_detect_defaults_to_terraform_when_no_env_config(
        self,
        mock_runner_registry: MagicMock,
        mock_event_manager: MagicMock,
        mock_providers: dict[str, Any],
    ) -> None:
        """Test that detect falls back to terraform when env config is missing."""
        mock_config_manager = MagicMock()
        mock_config_manager.load_environment.side_effect = FileNotFoundError("no config")
        mock_config_manager.get_all_resources_all_providers.return_value = []

        mock_runner = MagicMock()
        mock_runner_registry.create_runner.return_value = mock_runner

        detector = DriftDetector(
            config_manager=mock_config_manager,
            runner_registry=mock_runner_registry,
            event_manager=mock_event_manager,
            providers=mock_providers,
        )

        detector.detect("test-env")

        # Should fall back to "terraform"
        mock_runner_registry.create_runner.assert_called_once_with("terraform")


@pytest.mark.unit
class TestDriftDetectorUnparsedPlan:
    """An unparsable plan is reported as unknown drift, not as no drift (#1077)."""

    def _detect(
        self, plan_output: str, mock_runner_registry: MagicMock, mock_event_manager: MagicMock
    ) -> tuple[dict[str, Any], list[str], list[str]]:
        """Run ``detect`` on one provider whose plan prints ``plan_output``.

        Returns:
            The results, the warning messages and the info messages logged
        """
        config_manager = MagicMock()
        config_manager.load_environment.side_effect = FileNotFoundError("no config")
        config_manager.get_all_resources_all_providers.return_value = [
            SimpleNamespace(provider="proxmox")
        ]
        runner = TerraformRunner()
        mock_runner_registry.create_runner.return_value = runner
        detector = DriftDetector(
            config_manager=config_manager,
            runner_registry=mock_runner_registry,
            event_manager=mock_event_manager,
            providers={"proxmox": MagicMock()},
        )

        with (
            patch.object(runner, "plan", return_value={"success": True, "output": plan_output}),
            patch.object(detector, "_log_warning") as warn,
            patch.object(detector, "_log_info") as info,
        ):
            results = detector.detect("dev")

        warnings = [c.args[0] for c in warn.call_args_list]
        infos = [c.args[0] for c in info.call_args_list]
        return results, warnings, infos

    def test_unparsable_plan_warns_instead_of_reporting_no_drift(
        self, mock_runner_registry: MagicMock, mock_event_manager: MagicMock
    ) -> None:
        results, warnings, infos = self._detect(
            "Error: provider crashed", mock_runner_registry, mock_event_manager
        )

        assert results["proxmox"]["parsed"] is False
        assert results["proxmox"]["has_changes"] is False
        assert warnings == ["Could not determine drift for proxmox: Unable to parse plan output"]
        assert "No drift detected for proxmox" not in infos
        emitted = [c.args[0] for c in mock_event_manager.emit_event.call_args_list]
        assert EventType.DRIFT_DETECTED not in emitted

    def test_no_changes_plan_reports_no_drift(
        self, mock_runner_registry: MagicMock, mock_event_manager: MagicMock
    ) -> None:
        results, warnings, infos = self._detect(
            "No changes. Your infrastructure matches the configuration.",
            mock_runner_registry,
            mock_event_manager,
        )

        assert "parsed" not in results["proxmox"]
        assert warnings == []
        assert "No drift detected for proxmox" in infos
