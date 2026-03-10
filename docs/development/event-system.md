# Event System Guide

## Overview

InfraFoundry’s synchronous event system enables decoupled notifications, auditing, and lifecycle hooks across orchestration workflows.

## Audience and Prerequisites

- **Audience:** Contributors adding integrations, notifications, or custom side effects.
- **Prereqs:** Familiarity with Python and access to `src/infrafoundry/core/events.py`.

## When to Use This

- Emitting lifecycle/resource events from providers or workflows.
- Subscribing to deployment events for notifications or auditing.
- Extending drift/policy hooks.

## Quick Start

```python
from infrafoundry.core.events import Event, EventType, EventManager

def on_apply_complete(event: Event):
    print(f"Deployment {event.data.get('deployment_id')} finished in {event.environment}")

event_manager = EventManager()
event_manager.subscribe(EventType.AFTER_APPLY, on_apply_complete)
event_manager.emit_event(EventType.RESOURCE_CREATED, environment="prod", data={"resource_name": "web-01"})
```

## Architecture Details

- **Event types:** Lifecycle (`BEFORE/AFTER/FAILED` for PLAN/APPLY/DESTROY), runner lifecycle (`RUNNER_STARTING/COMPLETED/FAILED`), resource lifecycle (`RESOURCE_*`), drift (`DRIFT_*`), policy (`POLICY_*`), validation.
- **Event object:** `event_type`, `environment`, `data` (context), `timestamp`.
- **Managers:** `EventManager` supports `subscribe`, `subscribe_all`, and `emit_event`.
- **Integration:** `NotificationManager` listens to events and forwards to configured channels.

### Runner Lifecycle Events

Runner events are emitted in all three workflows (plan, apply, destroy) around each runner invocation:

- `RUNNER_STARTING` - Before `runner.plan()`, `runner.apply()`, or `runner.destroy()`
- `RUNNER_COMPLETED` - After a runner finishes successfully
- `RUNNER_FAILED` - When a runner raises an exception (the exception is re-raised)

The `EventContext` includes `provider` and `runner` fields, and the `data` dict carries a `RunnerEventData` payload with `provider`, `runner`, and optionally `success` or `error`.

**ScriptHandler** exposes the runner name as `INFRAFOUNDRY_RUNNER` environment variable, allowing scripts to filter by runner type:

| Variable | Set When |
| :--- | :--- |
| `INFRAFOUNDRY_ENV` | Always |
| `INFRAFOUNDRY_EVENT` | Always |
| `INFRAFOUNDRY_PROVIDER` | `context.provider` is set |
| `INFRAFOUNDRY_RESOURCE` | `context.resource` is set |
| `INFRAFOUNDRY_RUNNER` | `context.runner` is set |
| `INFRAFOUNDRY_CONFIG_DIR` | Always |
| `INFRAFOUNDRY_DEPLOYMENT_ID` | `context.deployment_id` is set |

**Example:** Run an Ansible playbook after Terraform finishes for a specific provider:

```yaml
events:
  - type: script
    on: runner_completed
    script: scripts/post-terraform.sh
    description: "Run post-Terraform Ansible setup"
```

```bash
#!/bin/bash
# scripts/post-terraform.sh
if [ "$INFRAFOUNDRY_RUNNER" = "terraform" ] && [ "$INFRAFOUNDRY_PROVIDER" = "proxmox" ]; then
    ansible-playbook -i inventory.yml site.yml
fi
```

## Validation and Checks

- Use consistent event types to ensure subscribers receive expected notifications.
- Include contextual data (e.g., `deployment_id`, `resource_name`) for consumers.
- Avoid heavy work in handlers to keep emission responsive.

## Examples

- **Subscribe to all events for audit logging:**
  ```python
  event_manager.subscribe_all(lambda e: log.info("%s %s", e.event_type, e.data))
  ```
- **Emit policy violation:**
  ```python
  event_manager.emit_event(
      EventType.POLICY_VIOLATION,
      environment="prod",
      data={"policy": "strict-naming", "resource": "vm-01"}
  )
  ```

## Related Documentation

- [Notifications Guide](../configuration/notifications.md)
- [Orchestrator Architecture](../architecture/orchestrator-architecture.md)
- [Policy Configuration Guide](../configuration/policy-configuration.md)

## Troubleshooting

- **Symptom:** Handlers not called. **Fix:** Ensure `subscribe` uses the correct `EventType`; check for multiple EventManager instances.
- **Symptom:** Missing context in notifications. **Fix:** Include required fields in `data` when emitting events.
- **Symptom:** Slow emission. **Fix:** Keep handlers lightweight or offload heavy work to async/background tasks.

---

Last updated: 2025-12-23 14:27 GMT


---
[Back to Table of Contents](../index.md)
