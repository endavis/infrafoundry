"""Automated drift remediation for infrastructure management."""

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from infrafoundry.core.config.models import DriftRemediationConfig
from infrafoundry.core.drift_detector import DriftDetector
from infrafoundry.core.events import EventManager, EventType
from infrafoundry.core.exceptions import InfraFoundryError


class DriftRemediationError(InfraFoundryError):
    """Error during drift remediation."""

    pass


class DriftRemediator:
    """Handles automated drift remediation with configurable thresholds.

    Provides safe drift remediation with:
    - Threshold-based auto-apply decisions
    - Separate limits for add/change/destroy operations
    - History tracking of remediation actions
    - Dry-run mode for safety
    - Event notifications for drift and remediation
    """

    def __init__(
        self,
        drift_detector: DriftDetector,
        event_manager: EventManager | None = None,
        history_dir: Path | None = None,
    ) -> None:
        """Initialize drift remediator.

        Args:
            drift_detector: Drift detector instance for detecting changes
            event_manager: Event manager for notifications (optional)
            history_dir: Directory for remediation history (defaults to ./.drift_history)
        """
        self.drift_detector = drift_detector
        self.event_manager = event_manager or EventManager()
        self.history_dir = history_dir or Path.cwd() / ".drift_history"
        self.history_dir.mkdir(parents=True, exist_ok=True)

    def should_auto_apply(
        self,
        drift_info: dict[str, Any],
        config: DriftRemediationConfig,
    ) -> tuple[bool, str]:
        """Determine if drift should be automatically remediated.

        Args:
            drift_info: Drift detection results with to_add, to_change, to_destroy counts
            config: Drift remediation configuration with thresholds

        Returns:
            Tuple of (should_apply, reason)
        """
        if not config.enabled:
            return False, "Drift remediation is disabled"

        if config.dry_run:
            return False, "Dry-run mode enabled - no auto-apply"

        if not drift_info.get("has_changes"):
            return False, "No drift detected"

        to_add = drift_info.get("to_add", 0)
        to_change = drift_info.get("to_change", 0)
        to_destroy = drift_info.get("to_destroy", 0)

        # Check total changes threshold
        total_changes = to_add + to_change + to_destroy
        if config.auto_apply_threshold == 0:
            return False, "Auto-apply threshold is 0 (disabled)"

        if total_changes > config.auto_apply_threshold:
            return (
                False,
                f"Total changes ({total_changes}) exceeds threshold "
                f"({config.auto_apply_threshold})",
            )

        # Check individual operation thresholds
        if to_add > config.max_to_add:
            return False, f"Resources to add ({to_add}) exceeds threshold ({config.max_to_add})"

        if to_change > config.max_to_change:
            return (
                False,
                f"Resources to change ({to_change}) exceeds threshold ({config.max_to_change})",
            )

        if to_destroy > config.max_to_destroy:
            return (
                False,
                f"Resources to destroy ({to_destroy}) exceeds threshold ({config.max_to_destroy})",
            )

        return True, f"Within thresholds (add:{to_add}, change:{to_change}, destroy:{to_destroy})"

    def remediate(
        self,
        env_name: str,
        config: DriftRemediationConfig,
        apply_fn: Callable[..., dict[str, Any]],
    ) -> dict[str, Any]:
        """Detect and remediate drift for an environment.

        Args:
            env_name: Environment name to check
            config: Drift remediation configuration
            apply_fn: Function to call for applying changes (orchestrator.apply)

        Returns:
            Dictionary with remediation results:
                - drift_detected: bool
                - auto_applied: bool
                - providers_with_drift: list[str]
                - remediation_results: dict[str, Any] (if applied)
                - reason: str (why auto-apply was/wasn't done)
                - timestamp: str
        """
        results: dict[str, Any] = {
            "drift_detected": False,
            "auto_applied": False,
            "providers_with_drift": [],
            "remediation_results": {},
            "reason": "",
            "timestamp": datetime.now().isoformat(),
            "env_name": env_name,
        }

        try:
            # Detect drift
            self.event_manager.emit_event(
                EventType.DRIFT_CHECK_STARTED,
                env_name,
                {"automated": True},
            )

            drift_results = self.drift_detector.detect(env_name)

            # Aggregate drift across all providers
            total_drift_info = {
                "has_changes": False,
                "to_add": 0,
                "to_change": 0,
                "to_destroy": 0,
            }

            providers_with_drift = []
            for provider_name, drift_info in drift_results.items():
                if drift_info.get("has_changes"):
                    providers_with_drift.append(provider_name)
                    total_drift_info["has_changes"] = True
                    total_drift_info["to_add"] += drift_info.get("to_add", 0)
                    total_drift_info["to_change"] += drift_info.get("to_change", 0)
                    total_drift_info["to_destroy"] += drift_info.get("to_destroy", 0)

            results["drift_detected"] = total_drift_info["has_changes"]
            results["providers_with_drift"] = providers_with_drift
            results["drift_info"] = total_drift_info

            # Notify on drift detection
            if total_drift_info["has_changes"] and config.notify_on_drift:
                self.event_manager.emit_event(
                    EventType.DRIFT_DETECTED,
                    env_name,
                    {
                        "providers": providers_with_drift,
                        "changes": total_drift_info,
                        "automated": True,
                    },
                )

            # Determine if we should auto-apply
            should_apply, reason = self.should_auto_apply(total_drift_info, config)
            results["reason"] = reason

            if should_apply:
                # Auto-apply remediation
                self.event_manager.emit_event(
                    EventType.BEFORE_APPLY,
                    env_name,
                    {
                        "automated": True,
                        "drift_remediation": True,
                        "changes": total_drift_info,
                    },
                )

                apply_results = apply_fn(env_name=env_name, auto_approve=True)
                results["auto_applied"] = True
                results["remediation_results"] = apply_results

                # Notify on successful remediation
                if config.notify_on_remediation:
                    self.event_manager.emit_event(
                        EventType.AFTER_APPLY,
                        env_name,
                        {
                            "automated": True,
                            "drift_remediation": True,
                            "results": apply_results,
                        },
                    )

            # Save to history
            self._save_history(results)

            return results

        except Exception as e:
            results["error"] = str(e)
            results["reason"] = f"Remediation failed: {e}"
            self._save_history(results)
            raise DriftRemediationError(f"Drift remediation failed for {env_name}: {e}") from e

    def get_history(
        self,
        env_name: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get remediation history.

        Args:
            env_name: Filter by environment name (optional)
            limit: Maximum number of history entries to return

        Returns:
            List of remediation history entries, newest first
        """
        history_files = sorted(
            self.history_dir.glob("remediation_*.yaml"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        history = []
        for history_file in history_files[: limit * 2]:  # Read extra in case filtering
            try:
                with open(history_file) as f:
                    entry = yaml.safe_load(f)
                    if env_name is None or entry.get("env_name") == env_name:
                        history.append(entry)
                        if len(history) >= limit:
                            break
            except Exception:
                continue  # Skip corrupted history files

        return history

    def _save_history(self, results: dict[str, Any]) -> None:
        """Save remediation results to history.

        Args:
            results: Remediation results to save
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        env_name = results.get("env_name", "unknown")
        history_file = self.history_dir / f"remediation_{env_name}_{timestamp}.yaml"

        try:
            with open(history_file, "w") as f:
                yaml.dump(results, f, default_flow_style=False)
        except Exception:
            # Don't fail remediation if history save fails
            # Silently ignore history save errors
            pass
