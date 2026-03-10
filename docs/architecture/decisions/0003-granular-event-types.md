# 3. Use Granular Lifecycle Event Types

**Date:** 2025-12-01
**Status:** Accepted

## Context
The orchestration workflow involves multiple stages (Plan, Apply, Destroy, Validate). We need a way to:
- Notify users (Slack, Discord) about progress and failures.
- Trigger audit logs.
- Allow plugins to hook into specific lifecycle points.

## Decision
We will define **19 granular event types** in the `EventType` enum, covering every major state transition.

- **Workflow Events:** `BEFORE_PLAN`, `AFTER_PLAN`, `PLAN_FAILED`, `BEFORE_APPLY`, etc.
- **Resource Events:** `RESOURCE_PLANNED`, `RESOURCE_CREATED`, `RESOURCE_UPDATED`, `RESOURCE_DESTROYED`.
- **System Events:** `DRIFT_DETECTED`, `POLICY_VIOLATION`.

## Consequences
**Positive:**
- **Observability:** Highly detailed insight into the execution flow.
- **Targeting:** Notifications can subscribe to specific events (e.g., "Only notify on `APPLY_FAILED`").
- **Audit:** Complete history of what happened to every resource.

**Negative:**
- **Noise:** Subscribing to "all" events generates a lot of data.
- **Maintenance:** Adding a new workflow step requires adding new event types to maintain consistency.

## Related Issues

- [#336](https://github.com/endavis/infrafoundry/issues/336) — Wire events config in settings.yaml to UnifiedEventBus

## Alternatives Considered
- **Generic Events (`LOG_INFO`, `LOG_ERROR`):** Rejected because it makes programmatic reaction (e.g., "trigger webhook on failure") difficult to parse.
- **Only Workflow-Level Events:** Rejected because we need resource-level granularity for audit trails.
