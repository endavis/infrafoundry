"""Unit tests for PolicyChecker."""

from io import StringIO
from unittest.mock import MagicMock

from rich.console import Console

from infrafoundry.core.events import EventType
from infrafoundry.core.policy.models import PolicyLevel, PolicyType, PolicyViolation
from infrafoundry.core.policy_checker import PolicyChecker


def _violation(level: PolicyLevel) -> PolicyViolation:
    return PolicyViolation(
        policy_name="test-policy",
        policy_type=PolicyType.REQUIRED_TAGS,
        level=level,
        resource_name="res1",
        provider="test",
        message="violation",
    )


def test_policy_checker_passes_when_no_violations():
    policy_engine = MagicMock()
    policy_engine.evaluate_resources.return_value = []
    event_manager = MagicMock()
    console = Console(file=StringIO(), force_terminal=False)

    checker = PolicyChecker(policy_engine, event_manager, console)
    passed, violations = checker.check("dev", [])

    assert passed is True
    assert violations == []
    event_manager.emit_event.assert_any_call(
        EventType.POLICY_CHECK_STARTED, "dev", {"resource_count": 0}
    )
    event_manager.emit_event.assert_any_call(
        EventType.POLICY_CHECK_PASSED, "dev", {"violations": 0}
    )


def test_policy_checker_warns_without_failing():
    policy_engine = MagicMock()
    policy_engine.evaluate_resources.return_value = [_violation(PolicyLevel.WARNING)]
    event_manager = MagicMock()
    console = Console(file=StringIO(), force_terminal=False)

    checker = PolicyChecker(policy_engine, event_manager, console)
    passed, violations = checker.check("dev", [{"name": "r"}])

    assert passed is True
    assert violations and violations[0].level is PolicyLevel.WARNING
    event_manager.emit_event.assert_any_call(
        EventType.POLICY_VIOLATION,
        "dev",
        {
            "policy": "test-policy",
            "resource": "res1",
            "level": "warning",
            "message": "violation",
        },
    )
    event_manager.emit_event.assert_any_call(
        EventType.POLICY_CHECK_PASSED, "dev", {"violations": 1}
    )


def test_policy_checker_enforce_errors_raises():
    policy_engine = MagicMock()
    policy_engine.evaluate_resources.return_value = [_violation(PolicyLevel.ERROR)]
    event_manager = MagicMock()
    console = Console(file=StringIO(), force_terminal=False)

    checker = PolicyChecker(policy_engine, event_manager, console)

    try:
        checker.check("dev", [{"name": "r"}], enforce=True)
    except Exception as exc:
        assert "Policy check failed" in str(exc)
    else:
        raise AssertionError("Expected exception not raised")

    event_manager.emit_event.assert_any_call(
        EventType.POLICY_VIOLATION,
        "dev",
        {
            "policy": "test-policy",
            "resource": "res1",
            "level": "error",
            "message": "violation",
        },
    )
    event_manager.emit_event.assert_any_call(
        EventType.POLICY_CHECK_FAILED, "dev", {"errors": 1, "warnings": 0}
    )
