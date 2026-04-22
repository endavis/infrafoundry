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

### Runner Lifecycle Events (Deprecated)

!!! warning "Deprecated"
    Runner lifecycle events are deprecated in favor of resource lifecycle events
    (`on_create`, `on_update`, `on_destroy`). They continue to work but emit
    `DeprecationWarning` messages. See [Resource Lifecycle Events](#resource-lifecycle-events).

Runner events are emitted in all three workflows (plan, apply, destroy) around each runner invocation:

- `RUNNER_STARTING` - Before `runner.plan()`, `runner.apply()`, or `runner.destroy()`
- `RUNNER_COMPLETED` - After a runner finishes successfully
- `RUNNER_FAILED` - When a runner raises an exception (the exception is re-raised)

The `EventContext` includes `provider` and `runner` fields, and the `data` dict carries a `RunnerEventData` payload with `provider`, `runner`, and optionally `success` or `error`.

### Configuring Event Handlers in settings.yaml

Event handlers are configured in your environment's `settings.yaml` under the `events:` key. The key is the event type name and the value is a list of handler configurations. Handlers are loaded at the start of each workflow (plan, apply, destroy).

!!! tip "Prefer Resource Lifecycle Events"
    For post-apply actions, use resource-level `on_create`/`on_update`/`on_destroy`
    events instead of `RUNNER_COMPLETED`. See [Resource Lifecycle Events](#resource-lifecycle-events).

```yaml
# envs/<env>/settings.yaml
events:
  DRIFT_DETECTED:
    - type: webhook
      url: "https://hooks.slack.com/..."
  AFTER_APPLY:
    - type: script
      name: "post-apply-notify"
      script: scripts/notify.sh
      timeout: 60
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
| `INFRAFOUNDRY_PACKAGE_DIR` | Handler is dispatched from a package context (always set when the handler comes from a package or its consumed blueprint). Absolute path to the consuming env package directory (e.g., `envs/prod/proxmox/ontap-cluster/`). Use this — not `$(dirname "$0")` — to locate runtime artifacts. |
| `INFRAFOUNDRY_DEPLOYMENT_ID` | `context.deployment_id` is set |
| `INFRAFOUNDRY_TARGET_RESOURCES` | `-r` filter is active (comma-separated list) |
| `INFRAFOUNDRY_INVENTORY` | Package has an `inventory:` block and a `.generated-inventory.yml` exists in the package directory |
| `INFRAFOUNDRY_WARNINGS_FILE` | An `infra apply` is in progress. Scripts may append non-fatal warnings as JSONL records (`{"source":"x","message":"y"}`); the framework renders a summary panel at the end of apply. On jumphost reexec, the file lives under the remote tmp dir and is scp'd back automatically. |

**Example (deprecated):** Run a script on `RUNNER_COMPLETED` (use resource lifecycle events instead):

```yaml
events:
  - type: script
    on: runner_completed
    script: scripts/post-terraform.sh
    description: "Run post-Terraform Ansible setup"
```

**Example (recommended):** Use resource lifecycle events for post-apply actions:

```yaml
vm:
  - name: web-server
    cores: 2
    memory: 4096
    events:
      on_create:
        - type: script
          name: post-provision
          script: scripts/post-provision.sh
          timeout: 300
```

### Jumphost Reexec

When a script handler's `EventContext.package_variables` contains a non-empty
`jumphost` key, the framework transparently runs the configured script on that
jumphost instead of the operator's workstation. This is how blueprints reach
API endpoints sitting on VLANs that are not directly routable from the
operator's host.

The mechanics are: `ScriptHandler` rsyncs the script's **parent directory** to
a fresh `/tmp/infrafoundry-<uuid>/` on the jumphost (so sibling helpers ship
along), then invokes the script over SSH. The remote process sees
`INFRAFOUNDRY_ON_JUMPHOST=1` (a recursion guard) and receives a stripped
`INFRAFOUNDRY_PACKAGE_VARS` JSON on stdin with the `jumphost` key removed, so
any downstream logic that branches on `jumphost` does not attempt a second
hop and so secrets never appear in the jumphost's `ps` output. The remote tmp
directory is always cleaned up, including on failure or timeout.

**Prerequisites on the jumphost:** `bash`, `rsync`, `ssh`, `python3`, plus any
tools the blueprint script itself needs. SSH must be reachable from the
operator's host using the value of `jumphost` as a destination (e.g.
`ansible@jump.example.com` or an alias defined in `~/.ssh/config`).

### Declaring script outputs

Blueprint event-handler scripts often produce artifact files the operator
needs on their workstation — a rendered kubeconfig, a CA cert, a deploy
report. When the script runs on a jumphost via the framework's reexec
path, those artifacts land on the jumphost, not on the operator's host,
because `~/…` expands against the jumphost's home directory. The `outputs:`
field on the script handler tells the framework which files to pull back
after a successful run.

```yaml
events:
  on_create:
    - type: script
      script: scripts/proxmox/k3s-post-terraform.sh
      outputs:
        - source: "/tmp/k3s-{{ cluster_name }}/kubeconfig.yaml"
          dest:   "{{ kubeconfig_local_path }}"
```

Local execution — the same declaration works for packages that don't set
`jumphost`; the framework uses `shutil.copy2` instead of `scp`:

```yaml
events:
  after_apply:
    - type: script
      script: scripts/render-report.sh
      outputs:
        - source: "/tmp/report-{{ environment }}.txt"
          dest:   "~/reports/{{ environment }}.txt"
```

Contract:

- `outputs:` is optional. Missing or empty means no pull-back (backwards
  compatible).
- Each entry is a mapping with two required string keys:
  - `source`: path on the **execution host** (the jumphost during
    reexec, the operator's host for local execution).
  - `dest`: path on the **operator's workstation**.
- Both values are Jinja2-rendered against the package variables. The
  same filter set the blueprint resolver uses is available.
- Both rendered paths must be absolute (start with `/` or `~`). A
  non-absolute value emits a warning and skips that entry without
  failing the handler. `~` is expanded on the operator side; on a
  jumphost source it is expanded by the remote shell via `scp`.
- Pull-back runs **only when the script succeeds** (exit code 0).
  Failed runs skip outputs processing entirely so partial artifacts
  don't leak to the operator.
- Transport:
  - Local execution: `shutil.copy2(source, dest)`; when `source == dest`
    the copy is a no-op.
  - Jumphost execution: one `scp` per entry, run between the remote
    warnings fetch and the remote tmp-dir cleanup so the source file
    still exists when `scp` runs.
- Parent directories of `dest` are created with `mkdir -p` automatically.
- Failure modes — missing source after success, non-zero scp, permission
  errors — are **non-fatal**. Each failure appends a warning to
  `INFRAFOUNDRY_WARNINGS_FILE` under the source tag
  `script_handler_outputs`, which surfaces in the apply summary panel.
- Permissions beyond what `scp` / `shutil.copy2` preserve are the
  script's responsibility (e.g. if the kubeconfig needs `chmod 600` on
  the operator host, the script that produced it should `chmod 600` it
  before `ScriptHandler` ships it back).

See [ADR-0006](../decisions/0006-explicit-script-handler-output-declarations.md)
for the design rationale and the alternatives that were considered.

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

## Resource Lifecycle Events

Resource lifecycle events fire based on the **actual outcome** of a terraform
apply or destroy, rather than on runner completion. This replaces the
`RUNNER_COMPLETED` pattern, which blocked subsequent providers.

### Event keys

| Event Key | Fires When | Maps to EventType |
|:----------|:-----------|:------------------|
| `on_create` | Terraform created the resource | `RESOURCE_CREATED` |
| `on_update` | Terraform updated the resource in place | `RESOURCE_UPDATED` |
| `on_destroy` | Terraform destroyed the resource | `RESOURCE_DELETED` |

### How it works

1. The IaC runner (Terraform/OpenTofu) runs with `-json` output
2. Structured JSON output is parsed into `ResourceOutcome` objects
3. After all IaC runners complete, outcomes are matched against each resource's
   `events` configuration
4. Matching handlers execute with resource context

### Declaring resource events

Events are declared directly on the resource definition:

```yaml
vm:
  - name: ontapcl-01
    cores: 4
    memory: 16384
    events:
      on_create:
        - type: script
          name: serial-setup
          script: scripts/ontap-serial-setup.sh
          timeout: 600
      on_destroy:
        - type: script
          name: cleanup
          script: scripts/ontap-cleanup.sh
```

### Non-IaC runner handling

Non-IaC runners (Ansible, PyInfra) are **skipped** during automatic
plan/apply/destroy execution. They are intended to run as resource lifecycle
event handlers instead. The `is_iac_runner` property on `BaseRunner` controls
this behavior.

### Environment variables

Scripts and playbooks receive resource context via environment variables:

| Variable | Description |
|:---------|:-----------|
| `INFRAFOUNDRY_EVENT` | Event type (e.g., `RESOURCE_CREATED`) |
| `INFRAFOUNDRY_RESOURCE` | Resource name that triggered the event |
| `INFRAFOUNDRY_PROVIDER` | Provider name |
| `INFRAFOUNDRY_PACKAGE` | Package name |
| `INFRAFOUNDRY_ENV` | Environment name |
| `INFRAFOUNDRY_CONFIG_DIR` | Path to environment config directory |
| `INFRAFOUNDRY_PACKAGE_DIR` | Absolute path to the consuming env package directory (e.g., `envs/prod/proxmox/ontap-cluster/`). Set when the handler is dispatched from a package context (always set when the handler comes from a package or its consumed blueprint). Use this — not `$(dirname "$0")` — to locate runtime artifacts. |
| `INFRAFOUNDRY_VAR_<key>` | Individual package variable (uppercase key) |
| `INFRAFOUNDRY_PACKAGE_VARS` | JSON dict of all merged package variables |
| `INFRAFOUNDRY_INVENTORY` | Absolute path to the package's `.generated-inventory.yml` (set only when the package defines an `inventory:` block) |
| `INFRAFOUNDRY_WARNINGS_FILE` | Per-apply JSONL warnings file (set during `infra apply`). Scripts may append records of the form `{"source":"x","message":"y"}`; the framework groups them by source and renders a summary panel at the end of apply. |

### Deprecation notice

The `RUNNER_STARTING` and `RUNNER_COMPLETED` events are deprecated. They
continue to work but emit `DeprecationWarning` messages. Migrate to
resource-level `on_create`, `on_update`, and `on_destroy` events.

## Resource-Scoped Event Handlers

Event handlers can be scoped to specific resources using the `resources` field.
When the `-r` CLI filter is active, only handlers whose `resources` list overlaps
with the targeted resources will fire. Handlers without a `resources` field always
fire regardless of the `-r` filter.

```yaml
events:
  AFTER_APPLY:
    - type: script
      script: scripts/cluster-setup.sh
      resources:
        - ontap-node1
        - ontap-node2
```

In this example, the script only runs when `ontap-node1` or `ontap-node2` is among
the resources targeted by `-r`. If no `-r` filter is used, all handlers fire.

Scripts receive the targeted resource names as a comma-separated list in the
`INFRAFOUNDRY_TARGET_RESOURCES` environment variable when the `-r` filter is active.

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

Last updated: 2026-03-18


---
[Back to Table of Contents](../index.md)
