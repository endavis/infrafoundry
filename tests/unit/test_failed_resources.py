"""Unit tests for the shared failed-resource marking helper."""

import logging
from unittest.mock import MagicMock

import pytest

from infrafoundry.core.events import EventType
from infrafoundry.core.failed_resources import mark_resources_failed
from infrafoundry.core.state import ResourceState

IDS = {"web": 1, "db": 2}


def _call(state: MagicMock, events: MagicMock, ids: dict[str, int] = IDS, **kw: object) -> None:
    kw.setdefault("phase", "apply")
    mark_resources_failed(state, events, "dev", "prov", ids, **kw)  # type: ignore[arg-type]


def test_marks_rows_error_and_emits_events() -> None:
    state, events = MagicMock(), MagicMock()
    _call(state, events)
    assert state.update_resource_state.call_args_list == [
        ((), {"resource_id": 1, "state": ResourceState.ERROR}),
        ((), {"resource_id": 2, "state": ResourceState.ERROR}),
    ]
    assert events.emit_event.call_count == 2
    events.emit_event.assert_any_call(
        EventType.RESOURCE_FAILED,
        "dev",
        {"resource_id": 1, "provider": "prov", "name": "web", "terraform_id": None},
        target_resources=["web"],
        package_filter=None,
        resource_scoped=True,
    )
    events.emit_event.assert_any_call(
        EventType.RESOURCE_FAILED,
        "dev",
        {"resource_id": 2, "provider": "prov", "name": "db", "terraform_id": None},
        target_resources=["db"],
        package_filter=None,
        resource_scoped=True,
    )


def test_package_filter_forwarded() -> None:
    state, events = MagicMock(), MagicMock()
    _call(state, events, {"web": 1}, package_filter="pkg")
    assert events.emit_event.call_args.kwargs["package_filter"] == "pkg"


def test_empty_map_is_noop() -> None:
    state, events = MagicMock(), MagicMock()
    _call(state, events, {})
    state.update_resource_state.assert_not_called()
    events.emit_event.assert_not_called()


@pytest.mark.parametrize("phase", ["apply", "destroy"])
def test_state_error_swallowed_and_logged(phase: str, caplog: pytest.LogCaptureFixture) -> None:
    state, events = MagicMock(), MagicMock()
    state.update_resource_state.side_effect = RuntimeError("boom")
    with caplog.at_level(logging.WARNING, logger="infrafoundry.core.failed_resources"):
        _call(state, events, phase=phase)
    assert f"after failed {phase} for provider prov" in caplog.text
    events.emit_event.assert_not_called()


def test_event_error_swallowed_and_logged(caplog: pytest.LogCaptureFixture) -> None:
    state, events = MagicMock(), MagicMock()
    events.emit_event.side_effect = RuntimeError("boom")
    with caplog.at_level(logging.WARNING, logger="infrafoundry.core.failed_resources"):
        _call(state, events, phase="destroy")
    assert "after failed destroy for provider prov" in caplog.text
