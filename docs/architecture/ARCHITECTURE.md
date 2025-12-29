# Infrastructure Architecture

## Overview

InfraFoundry’s architecture combines pluggable providers, template-driven code generation, an orchestrator, and state/event systems to enable drift detection, impact analysis, and controlled rollout/rollback.

## Audience and Prerequisites

- **Audience:** Contributors and operators who need to understand core components for extension or troubleshooting.
- **Prereqs:** Familiarity with Terraform/Ansible, basic Python, and access to the framework and config repos.

## When to Use This

- Investigating how InfraFoundry tracks deployments and dependencies.
- Extending providers, events, or runners.
- Explaining how plan/apply/destroy rely on state and the event bus.

## Quick Start

1. Generate + apply to see the flow in action:
   ```bash
   infra validate --env dev --check-api --check-refs
   infra plan --env dev
   infra apply --env dev
   ```
2. Inspect state and history:
   ```bash
   infra history --env dev
   infra status --env dev
   ```

## Architecture Details

- **State management:** `StateManager` (`src/infrafoundry/core/state.py`) persists deployments/resources/dependencies/events via SQLAlchemy. Default SQLite at `~/.infrafoundry/state.db`; PostgreSQL supported via `INFRAFOUNDRY_STATE_CONNECTION`.
- **Event system:** Pub/sub in `src/infrafoundry/core/events.py` with lifecycle events (`PLAN`, `APPLY`, `DESTROY`, resource lifecycle, validation, drift). Consumers subscribe for notifications, auditing, or custom automation.
- **Dependency graph:** Resources and provider rules produce a graph used for ordering creation/destruction and impact analysis.
- **Code generation:** Providers render Jinja2 templates into Terraform/Ansible under `generated/{env}/{terraform|ansible}/{provider}`.
- **Orchestration:** Orchestrator coordinates generation, runner invocation, and event emission; CLI drives user entry points.
- **Policies:** Pluggable policy engine validates resources before execution with warn/block levels.

## Validation and Checks

- Use `infra validate --env <env> --check-api --check-refs` to ensure configs, providers, and references are resolvable.
- Check state usage by running `infra history`/`infra status`; verify DB connectivity if using PostgreSQL.
- Review generated outputs before apply to confirm graph/order is correct.

## Examples

- **StateManager usage (conceptual):**
  ```python
  deployment_id = state_manager.create_deployment(environment="prod", command="apply", user="alice")
  state_manager.track_resource(deployment_id, environment="prod", provider="proxmox", resource_type="vm", name="web-01")
  state_manager.get_deployment_history(environment="prod", limit=50)
  ```
- **Event subscription:**
  ```python
  def on_created(event):
      log.info("Resource created %s", event.data["name"])
  event_manager.subscribe(EventType.RESOURCE_CREATED, on_created)
  ```

## Related Documentation

- [Architecture Overview](overview.md)
- [Orchestrator Architecture](orchestrator-architecture.md)
- [Pluggable Runners](pluggable-runners.md)
- [Secrets Architecture](secrets-architecture.md)
- [State Management](state-management.md)

## Troubleshooting

- **Symptom:** State/history missing. **Fix:** Confirm SQLite file exists or PostgreSQL DSN is reachable; check permissions.
- **Symptom:** Events not firing. **Fix:** Ensure subscribers are registered and event types match; enable debug logging.
- **Symptom:** Ordering issues. **Fix:** Review dependency graph output (`infra graph`) and provider reference definitions; validate configs with `--check-refs`.

---

Last updated: 2025-12-23 14:27 GMT


---
[Back to Table of Contents](../index.md)
