"""Event types for the unified event system."""

from enum import StrEnum


class EventType(StrEnum):
    """Types of events that can be emitted.

    Events are organized by category:
    - Phase events: Major workflow stages (plan, apply, destroy)
    - Provider events: Provider lifecycle
    - Runner events: Runner (terraform, ansible) lifecycle
    - Resource events: Individual resource lifecycle
    - Validation events: Config validation
    - Drift events: Drift detection
    - Policy events: Policy enforcement
    - Hook events: Lifecycle hook execution
    """

    # Planning phase
    BEFORE_PLAN = "before_plan"
    AFTER_PLAN = "after_plan"
    PLAN_FAILED = "plan_failed"

    # Apply phase
    BEFORE_APPLY = "before_apply"
    AFTER_APPLY = "after_apply"
    APPLY_FAILED = "apply_failed"

    # Destroy phase
    BEFORE_DESTROY = "before_destroy"
    AFTER_DESTROY = "after_destroy"
    DESTROY_FAILED = "destroy_failed"

    # Provider lifecycle
    PROVIDER_STARTING = "provider_starting"
    PROVIDER_COMPLETED = "provider_completed"
    PROVIDER_FAILED = "provider_failed"

    # Runner lifecycle
    RUNNER_STARTING = "runner_starting"
    RUNNER_COMPLETED = "runner_completed"
    RUNNER_FAILED = "runner_failed"

    # Resource lifecycle
    RESOURCE_PLANNED = "resource_planned"
    RESOURCE_CREATING = "resource_creating"
    RESOURCE_CREATED = "resource_created"
    RESOURCE_UPDATING = "resource_updating"
    RESOURCE_UPDATED = "resource_updated"
    RESOURCE_DELETING = "resource_deleting"
    RESOURCE_DELETED = "resource_deleted"
    RESOURCE_FAILED = "resource_failed"

    # Validation
    VALIDATION_STARTED = "validation_started"
    VALIDATION_PASSED = "validation_passed"
    VALIDATION_FAILED = "validation_failed"

    # Drift detection
    DRIFT_CHECK_STARTED = "drift_check_started"
    DRIFT_DETECTED = "drift_detected"
    DRIFT_CHECK_COMPLETED = "drift_check_completed"

    # Policy enforcement
    POLICY_CHECK_STARTED = "policy_check_started"
    POLICY_VIOLATION = "policy_violation"
    POLICY_CHECK_PASSED = "policy_check_passed"
    POLICY_CHECK_FAILED = "policy_check_failed"

    # Hook lifecycle
    HOOK_STARTED = "hook_started"
    HOOK_COMPLETED = "hook_completed"
    HOOK_FAILED = "hook_failed"


class HandlerType(StrEnum):
    """Types of event handlers."""

    PYTHON = "python"
    SCRIPT = "script"
    WEBHOOK = "webhook"


# Lifecycle stages that can have handlers configured
LIFECYCLE_STAGES = frozenset(
    {
        EventType.BEFORE_PLAN,
        EventType.AFTER_PLAN,
        EventType.BEFORE_APPLY,
        EventType.AFTER_APPLY,
        EventType.BEFORE_DESTROY,
        EventType.AFTER_DESTROY,
    }
)

# Events that support abort signals from handlers
ABORTABLE_EVENTS = frozenset(
    {
        EventType.BEFORE_PLAN,
        EventType.BEFORE_APPLY,
        EventType.BEFORE_DESTROY,
        EventType.POLICY_VIOLATION,
        EventType.DRIFT_DETECTED,
    }
)
