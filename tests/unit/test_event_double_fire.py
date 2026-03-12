"""Reproduce and verify fix for event handler double-firing during apply.

When orchestrator.apply() calls plan() then apply_orchestrator.apply(),
package event handlers should be registered exactly once during each phase.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from infrafoundry.core.events.bus import UnifiedEventBus
from infrafoundry.core.events.types import EventType


@pytest.mark.unit
class TestEventDoubleFireBug:
    """Tests for event handler double-firing during apply flow."""

    def _create_event_bus(self) -> UnifiedEventBus:
        """Create a fresh event bus for testing."""
        return UnifiedEventBus(
            config_base_dir=Path("/tmp/test"),
            console=MagicMock(),
        )

    def _sample_handler_config(self) -> dict:
        """Return a sample script handler config."""
        return {
            "type": "script",
            "name": "test-handler",
            "script": "scripts/test.sh",
        }

    def _sample_package_events(self) -> dict:
        """Return sample package events config."""
        return {
            "RUNNER_COMPLETED": [self._sample_handler_config()],
        }

    def test_clear_then_load_gives_one_handler(self):
        """After clear + load, exactly 1 handler should exist."""
        bus = self._create_event_bus()

        bus.clear_handlers()
        bus.load_config(self._sample_package_events())

        count = len(bus._handlers[EventType.RUNNER_COMPLETED])
        assert count == 1, f"Expected 1 handler, got {count}"

    def test_load_without_clear_accumulates(self):
        """Loading twice without clearing should give 2 handlers."""
        bus = self._create_event_bus()

        bus.load_config(self._sample_package_events())
        bus.load_config(self._sample_package_events())

        count = len(bus._handlers[EventType.RUNNER_COMPLETED])
        assert count == 2, f"Expected 2 handlers, got {count}"

    def test_clear_between_loads_gives_one_handler(self):
        """Clear between loads should give exactly 1 handler."""
        bus = self._create_event_bus()

        bus.load_config(self._sample_package_events())
        bus.clear_handlers()
        bus.load_config(self._sample_package_events())

        count = len(bus._handlers[EventType.RUNNER_COMPLETED])
        assert count == 1, f"Expected 1 handler, got {count}"

    def test_simulated_plan_then_apply_flow(self):
        """Simulate the exact orchestrator.apply() flow.

        Flow:
        1. Plan phase: clear_handlers → load_config (package events)
        2. Apply phase: clear_handlers → load_config (package events)

        After step 2, there should be exactly 1 handler.
        """
        bus = self._create_event_bus()
        events = self._sample_package_events()

        # --- Plan phase ---
        # _load_event_config: clear + load env events (none)
        bus.clear_handlers()
        # _load_resources: load package events
        bus.load_config(events)

        plan_count = len(bus._handlers[EventType.RUNNER_COMPLETED])
        assert plan_count == 1, f"Plan phase: expected 1 handler, got {plan_count}"

        # --- Apply phase ---
        # _load_event_config: clear + load env events (none)
        bus.clear_handlers()
        # _load_resources: load package events
        bus.load_config(events)

        apply_count = len(bus._handlers[EventType.RUNNER_COMPLETED])
        assert apply_count == 1, f"Apply phase: expected 1 handler, got {apply_count}"

    def test_simulated_flow_without_clear_between_phases(self):
        """If clear_handlers is NOT called between plan and apply, handlers double up.

        This simulates the bug scenario where package events are loaded
        additively without a clear in between.
        """
        bus = self._create_event_bus()
        events = self._sample_package_events()

        # Plan phase
        bus.clear_handlers()
        bus.load_config(events)

        # Apply phase - NO clear_handlers before load
        bus.load_config(events)

        apply_count = len(bus._handlers[EventType.RUNNER_COMPLETED])
        assert apply_count == 2, f"Expected 2 handlers (bug), got {apply_count}"

    def test_env_events_plus_package_events(self):
        """Env settings events and package events should coexist."""
        bus = self._create_event_bus()
        env_events = {
            "BEFORE_APPLY": [{"type": "script", "name": "env-handler", "script": "scripts/env.sh"}],
        }
        package_events = self._sample_package_events()

        # _load_event_config: clear + load env events
        bus.clear_handlers()
        bus.load_config(env_events)

        # _load_resources: load package events (additive)
        bus.load_config(package_events)

        env_count = len(bus._handlers[EventType.BEFORE_APPLY])
        pkg_count = len(bus._handlers[EventType.RUNNER_COMPLETED])
        assert env_count == 1, f"Expected 1 env handler, got {env_count}"
        assert pkg_count == 1, f"Expected 1 package handler, got {pkg_count}"

    def test_provider_centric_loader_clears_pending_events(self):
        """get_package_events should return events and clear the buffer."""
        from infrafoundry.core.config.provider_centric_loader import ProviderCentricLoader

        loader = ProviderCentricLoader(Path("/tmp/test"))

        # Simulate accumulating events
        loader._pending_package_events = {"RUNNER_COMPLETED": [self._sample_handler_config()]}

        # First call returns events and clears
        events = loader.get_package_events()
        assert "RUNNER_COMPLETED" in events
        assert len(events["RUNNER_COMPLETED"]) == 1

        # Second call returns empty
        events2 = loader.get_package_events()
        assert events2 == {}

    def test_full_load_resources_flow(self):
        """Simulate _load_resources with mocked config_manager.

        Verifies that get_all_resources_all_providers populates events
        and get_package_events returns and clears them correctly.
        """
        bus = self._create_event_bus()
        events = self._sample_package_events()

        # Simulate _load_event_config
        bus.clear_handlers()

        # Simulate _load_resources
        # 1. get_all_resources_all_providers → populates _pending_package_events
        # 2. get_package_events → returns and clears
        # 3. load_config → registers handlers
        bus.load_config(events)

        assert len(bus._handlers[EventType.RUNNER_COMPLETED]) == 1

        # Now simulate the SECOND phase (apply after plan)
        bus.clear_handlers()
        bus.load_config(events)

        assert len(bus._handlers[EventType.RUNNER_COMPLETED]) == 1

    def test_stale_pending_events_cleared_on_reload(self):
        """Verify fix for #352: stale _pending_package_events from callers
        that don't drain the buffer (e.g., build_dependency_graph).

        get_all_resources_all_providers must clear _pending_package_events
        at the start so stale events from prior calls don't accumulate.
        """
        from unittest.mock import patch

        from infrafoundry.core.config.config_manager import ConfigManager

        cm = ConfigManager(Path("/tmp/nonexistent"))

        # Simulate stale events left by build_dependency_graph
        cm.provider_centric._pending_package_events = {
            "RUNNER_COMPLETED": [self._sample_handler_config()]
        }

        # get_all_resources_all_providers should clear stale events first
        with patch.object(cm.provider_centric, "discover_providers", return_value=set()):
            cm.get_all_resources_all_providers("test")

        # After the call, pending events should only contain events from
        # this call (none, since no providers were discovered)
        events = cm.get_package_events()
        assert events == {}, f"Expected empty events, got {events}"

    def test_pending_events_not_stale_across_calls(self):
        """Verify that consecutive get_all_resources_all_providers calls
        each return exactly the events from that call, not accumulated.
        """
        from unittest.mock import patch

        from infrafoundry.core.config.config_manager import ConfigManager

        cm = ConfigManager(Path("/tmp/nonexistent"))

        handler = self._sample_handler_config()

        # First call accumulates 1 event but we don't drain
        cm.provider_centric._pending_package_events = {"RUNNER_COMPLETED": [handler]}

        # Second call should start fresh (clearing stale events)
        with patch.object(cm.provider_centric, "discover_providers", return_value=set()):
            cm.get_all_resources_all_providers("test")

        events = cm.get_package_events()
        # Should be empty since no providers discovered (stale was cleared)
        assert events == {}
