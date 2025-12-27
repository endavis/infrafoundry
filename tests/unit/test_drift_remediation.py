"""Unit tests for drift remediation functionality."""

from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest
import yaml

from infrafoundry.core.config.models import DriftRemediationConfig
from infrafoundry.core.drift_remediation import DriftRemediationError, DriftRemediator
from infrafoundry.core.events import EventManager


@pytest.fixture
def mock_drift_detector():
    """Create a mock drift detector."""
    detector = MagicMock()
    detector.detect = MagicMock()
    return detector


@pytest.fixture
def mock_event_manager():
    """Create a mock event manager."""
    return MagicMock(spec=EventManager)


@pytest.fixture
def temp_history_dir(tmp_path):
    """Create a temporary history directory."""
    history_dir = tmp_path / ".drift_history"
    history_dir.mkdir()
    return history_dir


@pytest.fixture
def remediator(mock_drift_detector, mock_event_manager, temp_history_dir):
    """Create a DriftRemediator instance for testing."""
    return DriftRemediator(
        drift_detector=mock_drift_detector,
        event_manager=mock_event_manager,
        history_dir=temp_history_dir,
    )


@pytest.mark.unit
class TestDriftRemediationConfig:
    """Tests for DriftRemediationConfig model."""

    def test_default_config(self):
        """Test default configuration values."""
        config = DriftRemediationConfig()

        assert config.enabled is False
        assert config.check_interval_minutes == 60
        assert config.auto_apply_threshold == 5
        assert config.max_to_add == 3
        assert config.max_to_change == 3
        assert config.max_to_destroy == 0
        assert config.notify_on_drift is True
        assert config.notify_on_remediation is True
        assert config.dry_run is False

    def test_custom_config(self):
        """Test custom configuration values."""
        config = DriftRemediationConfig(
            enabled=True,
            check_interval_minutes=30,
            auto_apply_threshold=10,
            max_to_add=5,
            max_to_change=5,
            max_to_destroy=2,
            dry_run=True,
        )

        assert config.enabled is True
        assert config.check_interval_minutes == 30
        assert config.auto_apply_threshold == 10
        assert config.max_to_add == 5
        assert config.max_to_change == 5
        assert config.max_to_destroy == 2
        assert config.dry_run is True

    def test_validation_minimum_interval(self):
        """Test validation of minimum check interval."""
        with pytest.raises(ValueError):
            DriftRemediationConfig(check_interval_minutes=0)

    def test_validation_negative_thresholds(self):
        """Test validation prevents negative thresholds."""
        with pytest.raises(ValueError):
            DriftRemediationConfig(auto_apply_threshold=-1)

        with pytest.raises(ValueError):
            DriftRemediationConfig(max_to_add=-1)


@pytest.mark.unit
class TestDriftRemediatorInit:
    """Tests for DriftRemediator initialization."""

    def test_initialization(self, mock_drift_detector, mock_event_manager, temp_history_dir):
        """Test remediator initialization."""
        remediator = DriftRemediator(
            drift_detector=mock_drift_detector,
            event_manager=mock_event_manager,
            history_dir=temp_history_dir,
        )

        assert remediator.drift_detector == mock_drift_detector
        assert remediator.event_manager == mock_event_manager
        assert remediator.history_dir == temp_history_dir

    def test_default_event_manager(self, mock_drift_detector, temp_history_dir):
        """Test default event manager creation."""
        remediator = DriftRemediator(
            drift_detector=mock_drift_detector,
            history_dir=temp_history_dir,
        )

        assert remediator.event_manager is not None
        assert isinstance(remediator.event_manager, EventManager)

    def test_default_history_dir(self, mock_drift_detector):
        """Test default history directory creation."""
        remediator = DriftRemediator(drift_detector=mock_drift_detector)

        assert remediator.history_dir == Path.cwd() / ".drift_history"


@pytest.mark.unit
class TestShouldAutoApply:
    """Tests for should_auto_apply method."""

    def test_disabled_remediation(self, remediator):
        """Test that disabled remediation is not auto-applied."""
        config = DriftRemediationConfig(enabled=False)
        drift_info = {"has_changes": True, "to_add": 1, "to_change": 1, "to_destroy": 0}

        should_apply, reason = remediator.should_auto_apply(drift_info, config)

        assert should_apply is False
        assert "disabled" in reason.lower()

    def test_dry_run_mode(self, remediator):
        """Test that dry-run mode prevents auto-apply."""
        config = DriftRemediationConfig(enabled=True, dry_run=True)
        drift_info = {"has_changes": True, "to_add": 1, "to_change": 1, "to_destroy": 0}

        should_apply, reason = remediator.should_auto_apply(drift_info, config)

        assert should_apply is False
        assert "dry-run" in reason.lower()

    def test_no_changes(self, remediator):
        """Test that no drift means no auto-apply."""
        config = DriftRemediationConfig(enabled=True)
        drift_info = {"has_changes": False, "to_add": 0, "to_change": 0, "to_destroy": 0}

        should_apply, reason = remediator.should_auto_apply(drift_info, config)

        assert should_apply is False
        assert "no drift" in reason.lower()

    def test_zero_threshold(self, remediator):
        """Test that zero threshold disables auto-apply."""
        config = DriftRemediationConfig(enabled=True, auto_apply_threshold=0)
        drift_info = {"has_changes": True, "to_add": 1, "to_change": 0, "to_destroy": 0}

        should_apply, reason = remediator.should_auto_apply(drift_info, config)

        assert should_apply is False
        assert "threshold is 0" in reason.lower()

    def test_exceeds_total_threshold(self, remediator):
        """Test that exceeding total threshold prevents auto-apply."""
        config = DriftRemediationConfig(enabled=True, auto_apply_threshold=3)
        drift_info = {"has_changes": True, "to_add": 2, "to_change": 2, "to_destroy": 0}

        should_apply, reason = remediator.should_auto_apply(drift_info, config)

        assert should_apply is False
        assert "exceeds threshold" in reason.lower()

    def test_exceeds_add_threshold(self, remediator):
        """Test that exceeding add threshold prevents auto-apply."""
        config = DriftRemediationConfig(
            enabled=True,
            auto_apply_threshold=10,
            max_to_add=2,
        )
        drift_info = {"has_changes": True, "to_add": 3, "to_change": 1, "to_destroy": 0}

        should_apply, reason = remediator.should_auto_apply(drift_info, config)

        assert should_apply is False
        assert "to add" in reason.lower()

    def test_exceeds_change_threshold(self, remediator):
        """Test that exceeding change threshold prevents auto-apply."""
        config = DriftRemediationConfig(
            enabled=True,
            auto_apply_threshold=10,
            max_to_change=2,
        )
        drift_info = {"has_changes": True, "to_add": 1, "to_change": 3, "to_destroy": 0}

        should_apply, reason = remediator.should_auto_apply(drift_info, config)

        assert should_apply is False
        assert "to change" in reason.lower()

    def test_exceeds_destroy_threshold(self, remediator):
        """Test that exceeding destroy threshold prevents auto-apply."""
        config = DriftRemediationConfig(
            enabled=True,
            auto_apply_threshold=10,
            max_to_destroy=0,
        )
        drift_info = {"has_changes": True, "to_add": 1, "to_change": 1, "to_destroy": 1}

        should_apply, reason = remediator.should_auto_apply(drift_info, config)

        assert should_apply is False
        assert "to destroy" in reason.lower()

    def test_within_all_thresholds(self, remediator):
        """Test successful auto-apply when within all thresholds."""
        config = DriftRemediationConfig(
            enabled=True,
            auto_apply_threshold=10,
            max_to_add=3,
            max_to_change=3,
            max_to_destroy=1,
        )
        drift_info = {"has_changes": True, "to_add": 2, "to_change": 2, "to_destroy": 1}

        should_apply, reason = remediator.should_auto_apply(drift_info, config)

        assert should_apply is True
        assert "within thresholds" in reason.lower()


@pytest.mark.unit
class TestRemediate:
    """Tests for remediate method."""

    def test_no_drift_detected(self, remediator, mock_drift_detector):
        """Test remediation when no drift is detected."""
        mock_drift_detector.detect.return_value = {
            "proxmox": {"has_changes": False, "to_add": 0, "to_change": 0, "to_destroy": 0}
        }

        config = DriftRemediationConfig(enabled=True)
        mock_apply = Mock()

        result = remediator.remediate("dev", config, mock_apply)

        assert result["drift_detected"] is False
        assert result["auto_applied"] is False
        assert result["providers_with_drift"] == []
        mock_apply.assert_not_called()

    def test_drift_detected_not_applied(self, remediator, mock_drift_detector):
        """Test drift detection without auto-apply (exceeds threshold)."""
        mock_drift_detector.detect.return_value = {
            "proxmox": {"has_changes": True, "to_add": 10, "to_change": 5, "to_destroy": 0}
        }

        config = DriftRemediationConfig(
            enabled=True,
            auto_apply_threshold=5,  # Less than total changes (15)
        )
        mock_apply = Mock()

        result = remediator.remediate("dev", config, mock_apply)

        assert result["drift_detected"] is True
        assert result["auto_applied"] is False
        assert "proxmox" in result["providers_with_drift"]
        assert "exceeds threshold" in result["reason"]
        mock_apply.assert_not_called()

    def test_drift_detected_and_applied(self, remediator, mock_drift_detector):
        """Test successful drift remediation with auto-apply."""
        mock_drift_detector.detect.return_value = {
            "proxmox": {"has_changes": True, "to_add": 2, "to_change": 1, "to_destroy": 0}
        }

        config = DriftRemediationConfig(
            enabled=True,
            auto_apply_threshold=5,
            max_to_add=3,
            max_to_change=3,
        )
        mock_apply = Mock(return_value={"proxmox": {"status": "success"}})

        result = remediator.remediate("dev", config, mock_apply)

        assert result["drift_detected"] is True
        assert result["auto_applied"] is True
        assert result["providers_with_drift"] == ["proxmox"]
        assert "within thresholds" in result["reason"].lower()
        mock_apply.assert_called_once_with(env_name="dev", auto_approve=True)

    def test_drift_multiple_providers(self, remediator, mock_drift_detector):
        """Test drift detection across multiple providers."""
        mock_drift_detector.detect.return_value = {
            "proxmox": {"has_changes": True, "to_add": 1, "to_change": 1, "to_destroy": 0},
            "opnsense": {"has_changes": True, "to_add": 1, "to_change": 0, "to_destroy": 0},
            "kea": {"has_changes": False, "to_add": 0, "to_change": 0, "to_destroy": 0},
        }

        config = DriftRemediationConfig(enabled=True, auto_apply_threshold=5)
        mock_apply = Mock(return_value={})

        result = remediator.remediate("dev", config, mock_apply)

        assert result["drift_detected"] is True
        assert set(result["providers_with_drift"]) == {"proxmox", "opnsense"}
        assert result["drift_info"]["to_add"] == 2
        assert result["drift_info"]["to_change"] == 1

    def test_dry_run_mode(self, remediator, mock_drift_detector):
        """Test that dry-run mode doesn't apply changes."""
        mock_drift_detector.detect.return_value = {
            "proxmox": {"has_changes": True, "to_add": 1, "to_change": 0, "to_destroy": 0}
        }

        config = DriftRemediationConfig(enabled=True, dry_run=True)
        mock_apply = Mock()

        result = remediator.remediate("dev", config, mock_apply)

        assert result["drift_detected"] is True
        assert result["auto_applied"] is False
        assert "dry-run" in result["reason"].lower()
        mock_apply.assert_not_called()

    def test_remediation_failure(self, remediator, mock_drift_detector):
        """Test handling of remediation failures."""
        mock_drift_detector.detect.side_effect = Exception("Drift detection failed")

        config = DriftRemediationConfig(enabled=True)
        mock_apply = Mock()

        with pytest.raises(DriftRemediationError, match="Drift detection failed"):
            remediator.remediate("dev", config, mock_apply)

    def test_event_emissions(self, remediator, mock_drift_detector, mock_event_manager):
        """Test that appropriate events are emitted during remediation."""
        mock_drift_detector.detect.return_value = {
            "proxmox": {"has_changes": True, "to_add": 1, "to_change": 1, "to_destroy": 0}
        }

        config = DriftRemediationConfig(
            enabled=True,
            auto_apply_threshold=5,
            notify_on_drift=True,
            notify_on_remediation=True,
        )
        mock_apply = Mock(return_value={"proxmox": {"status": "success"}})

        remediator.remediate("dev", config, mock_apply)

        # Verify events were emitted (Drift Check Started, Drift Detected,
        # Before Apply, After Apply)
        assert mock_event_manager.emit_event.call_count >= 3


@pytest.mark.unit
class TestHistory:
    """Tests for remediation history functionality."""

    def test_save_history(self, remediator, mock_drift_detector, temp_history_dir):
        """Test that remediation results are saved to history."""
        mock_drift_detector.detect.return_value = {
            "proxmox": {"has_changes": False, "to_add": 0, "to_change": 0, "to_destroy": 0}
        }

        config = DriftRemediationConfig(enabled=True)
        mock_apply = Mock()

        remediator.remediate("dev", config, mock_apply)

        # Verify history file was created
        history_files = list(temp_history_dir.glob("remediation_dev_*.yaml"))
        assert len(history_files) == 1

        # Verify content
        with open(history_files[0]) as f:
            history = yaml.safe_load(f)
            assert history["env_name"] == "dev"
            assert history["drift_detected"] is False

    def test_get_history_empty(self, remediator):
        """Test retrieving history when none exists."""
        history = remediator.get_history()

        assert history == []

    def test_get_history_with_entries(self, remediator, temp_history_dir):
        """Test retrieving history entries."""
        # Create some history files
        for i in range(3):
            history_file = temp_history_dir / f"remediation_dev_20250101_00000{i}.yaml"
            data = {
                "env_name": "dev",
                "drift_detected": i % 2 == 0,
                "auto_applied": False,
                "timestamp": f"2025-01-01T00:00:0{i}",
            }
            with open(history_file, "w") as f:
                yaml.dump(data, f)

        history = remediator.get_history(limit=10)

        assert len(history) == 3

    def test_get_history_with_env_filter(self, remediator, temp_history_dir):
        """Test filtering history by environment."""
        # Create history for different environments with unique timestamps
        for i, env in enumerate(["dev", "prod", "dev"]):
            history_file = temp_history_dir / f"remediation_{env}_20250101_00000{i}.yaml"
            data = {"env_name": env, "drift_detected": True}
            with open(history_file, "w") as f:
                yaml.dump(data, f)

        history = remediator.get_history(env_name="dev")

        assert len(history) == 2
        assert all(h["env_name"] == "dev" for h in history)

    def test_get_history_with_limit(self, remediator, temp_history_dir):
        """Test limiting history results."""
        # Create more entries than the limit
        for i in range(15):
            history_file = temp_history_dir / f"remediation_dev_20250101_00000{i:02d}.yaml"
            data = {"env_name": "dev", "drift_detected": True}
            with open(history_file, "w") as f:
                yaml.dump(data, f)

        history = remediator.get_history(limit=5)

        assert len(history) == 5

    def test_history_corrupted_file_skipped(self, remediator, temp_history_dir):
        """Test that corrupted history files are skipped."""
        # Create a valid history file
        valid_file = temp_history_dir / "remediation_dev_20250101_000001.yaml"
        with open(valid_file, "w") as f:
            yaml.dump({"env_name": "dev"}, f)

        # Create a corrupted file
        corrupted_file = temp_history_dir / "remediation_dev_20250101_000000.yaml"
        with open(corrupted_file, "w") as f:
            f.write("invalid: yaml: content: [[[")

        history = remediator.get_history()

        # Should only get the valid entry
        assert len(history) == 1
        assert history[0]["env_name"] == "dev"
