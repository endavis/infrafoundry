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

### Configuring Event Handlers in settings.yaml

Event handlers are configured in your environment's `settings.yaml` under the `events:` key. The key is the event type name and the value is a list of handler configurations. Handlers are loaded at the start of each workflow (plan, apply, destroy).

```yaml
# envs/<env>/settings.yaml
events:
  RUNNER_COMPLETED:
    - type: script
      name: "ontap-setup"
      script: scripts/ontap-post-terraform.sh
      timeout: 600
  DRIFT_DETECTED:
    - type: webhook
      url: "https://hooks.slack.com/..."
```

**ScriptHandler** exposes the runner name as `INFRAFOUNDRY_RUNNER` environment variable, allowing scripts to filter by runner type:

| Variable | Set When |
| :--- | :--- |
| `INFRAFOUNDRY_ENV` | Always |
| `INFRAFOUNDRY_EVENT` | Always |
| `INFRAFOUNDRY_PROVIDER` | `context.provider` is set |
| `INFRAFOUNDRY_RESOURCE` | `context.resource` is set |
| `INFRAFOUNDRY_RUNNER` | `context.runner` is set |
| `INFRAFOUNDRY_PHASE` | `data.phase` is set (`plan`, `apply`, or `destroy`) |
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
if [ "$INFRAFOUNDRY_RUNNER" = "terraform" ] && [ "$INFRAFOUNDRY_PROVIDER" = "proxmox" ] && [ "${INFRAFOUNDRY_PHASE:-}" = "apply" ]; then
    ansible-playbook -i inventory.yml site.yml
fi
```

### Real-Time Output Streaming

Script handlers stream stdout and stderr to the console in real-time, line by line, instead of buffering all output until the script completes. This is essential for long-running handlers (e.g., Ansible playbooks) where the user needs to see progress.

- **stdout** lines are printed with 4-space indent
- **stderr** lines are printed with 4-space indent and `[red]` Rich styling
- Output is still captured in `EventResult.stdout` and `EventResult.stderr` for programmatic use
- The summary line (success/failure) is printed after the script finishes, but the output is not re-printed since it was already streamed
- When no console is available (e.g., programmatic usage), output is captured silently as before

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

## Package Events

Infrastructure packages can declare event handlers in their `infrafoundry.yml` manifest.
These events use the same format as environment-level events in `settings.yaml`, but
script paths are automatically rewritten to be relative to the environment directory.

Package events are discovered during resource loading and registered with the event bus
after all resources have been loaded. This happens in `Orchestrator._load_resources()`.

```yaml
# envs/dev/proxmox/ontap-cluster/infrafoundry.yml
events:
  AFTER_APPLY:
    - type: script
      script: scripts/cluster-setup.sh
      timeout: 300
```

The script path `scripts/cluster-setup.sh` is rewritten to
`proxmox/ontap-cluster/scripts/cluster-setup.sh` so that ScriptHandler resolves it
correctly from the environment directory.

See the [Infrastructure Packages guide](../configuration/infrastructure-packages.md)
for full details on package structure and configuration.

## Related Documentation

- [Infrastructure Packages](../configuration/infrastructure-packages.md)
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
