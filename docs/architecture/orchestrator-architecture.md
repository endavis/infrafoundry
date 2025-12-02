# Orchestrator Architecture

## Overview

The Orchestrator is a thin coordinator that wires providers, runners, policy checks, drift detection, state, events, and notifications. Dedicated workflow classes handle plan/apply/destroy/rollback/status while the Orchestrator focuses on delegation and ordering.

## Audience and Prerequisites

- **Audience:** Contributors extending orchestration workflows or debugging execution order.
- **Prereqs:** Understanding of InfraFoundry providers, runners, and state/event systems.

## When to Use This

- Tracing how plan/apply/destroy invoke helpers.
- Adding new workflow steps or hooks.
- Ensuring providers are registered and grouped correctly.

## Quick Start

1. Run a workflow to see orchestration in action:
   ```bash
   infra plan --env dev
   infra apply --env dev
   infra destroy --env dev
   ```
2. Inspect generated artifacts and events to verify order and outputs.

## Architecture Details

- **Delegation pattern:** Top-level Orchestrator is a facade; workflow classes (`Validation/Plan/Apply/Destroy/Rollback/Drift/Status` orchestrators in `core/orchestrator_workflows.py`) implement steps.
- **Helpers coordinated:**
  - ConfigManager (resource loading/validation)
  - PolicyEngine (pre-deployment checks)
  - Dependency graph builder (ordering)
  - SecretManager (exports for Terraform/Ansible)
  - Providers (render Terraform/Ansible)
  - Runners via DeploymentExecutor (Terraform/Ansible execution)
  - StateManager (deployments/resources/events)
  - EventManager (BEFORE/AFTER/FAILED events across lifecycle)
  - NotificationManager (subscribed to events)
- **Workflow outline:**
  1. Create deployment record; emit BEFORE event.
  2. Load/validate resources; check policies; group by provider.
  3. Track resources in state; render Terraform/Ansible; export secrets.
  4. Execute via runners; update state; emit AFTER or FAILED events.
- **Provider registry:** Providers registered once; grouped resources dispatched per provider.

## Workflow Sequence Diagrams

The following sequence diagrams illustrate the interaction flow between components during key workflows.

### Plan Workflow

```mermaid
sequenceDiagram
    actor User
    participant CLI
    participant Orchestrator
    participant PlanOrchestrator
    participant StateManager
    participant EventManager
    participant ConfigManager
    participant PolicyEngine
    participant Provider
    participant SecretManager
    participant Runner

    User->>CLI: infra plan --env dev
    CLI->>Orchestrator: plan(env_name, dry_run, resource_filter)
    Orchestrator->>PlanOrchestrator: plan(env_name, dry_run, resource_filter, enforce_policies)

    PlanOrchestrator->>StateManager: create_deployment(env, "plan", user, dry_run, metadata)
    StateManager-->>PlanOrchestrator: deployment_id

    PlanOrchestrator->>EventManager: emit_event(BEFORE_PLAN, env, data)
    EventManager-->>PlanOrchestrator: event emitted

    PlanOrchestrator->>ConfigManager: load_resources(env_name)
    ConfigManager-->>PlanOrchestrator: all_resources, resources_by_provider

    alt has policies
        PlanOrchestrator->>PolicyEngine: check_policies(env, resources, enforce)
        PolicyEngine-->>PlanOrchestrator: policy results
    end

    loop for each provider
        PlanOrchestrator->>PlanOrchestrator: validate_resources(provider_resources)

        PlanOrchestrator->>StateManager: track_resource(deployment_id, env, provider, resource, PLANNED)
        StateManager-->>PlanOrchestrator: tracked_resource

        PlanOrchestrator->>EventManager: emit_event(RESOURCE_PLANNED, env, resource_data)

        alt not dry_run
            PlanOrchestrator->>Provider: set_environment(env_name)
            PlanOrchestrator->>Provider: ensure_directories()

            PlanOrchestrator->>SecretManager: export_for_terraform(secrets_file, tf_vars)
            SecretManager-->>PlanOrchestrator: secrets exported

            loop for each runner (terraform, ansible, etc.)
                PlanOrchestrator->>Provider: generate_{tool}(resources)
                Provider-->>PlanOrchestrator: config generated

                PlanOrchestrator->>Runner: run(provider, "plan", auto_approve=False)
                Runner-->>PlanOrchestrator: runner_result
            end
        end
    end

    PlanOrchestrator->>StateManager: update_deployment_status(deployment_id, COMPLETED)
    PlanOrchestrator->>EventManager: emit_event(AFTER_PLAN, env, results)

    PlanOrchestrator-->>Orchestrator: results
    Orchestrator-->>CLI: results
    CLI-->>User: plan output displayed
```

### Apply Workflow

```mermaid
sequenceDiagram
    actor User
    participant CLI
    participant Orchestrator
    participant ApplyOrchestrator
    participant StateManager
    participant EventManager
    participant ConfigManager
    participant Provider
    participant SecretManager
    participant Runner

    User->>CLI: infra apply --env dev
    CLI->>Orchestrator: apply(env_name, resource_filter, auto_approve, parallel, max_workers)
    Orchestrator->>ApplyOrchestrator: apply(env_name, resource_filter, auto_approve, parallel, max_workers)

    ApplyOrchestrator->>StateManager: create_deployment(env, "apply", user, False, metadata)
    StateManager-->>ApplyOrchestrator: deployment_id

    ApplyOrchestrator->>EventManager: emit_event(BEFORE_APPLY, env, data)
    EventManager-->>ApplyOrchestrator: event emitted

    ApplyOrchestrator->>ConfigManager: load_resources(env_name)
    ConfigManager-->>ApplyOrchestrator: all_resources, resources_by_provider

    ApplyOrchestrator->>StateManager: update_deployment_rollback_data(deployment_id, snapshot)
    StateManager-->>ApplyOrchestrator: rollback data stored

    alt parallel and multiple providers
        ApplyOrchestrator->>ApplyOrchestrator: apply_parallel(env, deployment_id, resources, filter, approve, workers)
        Note over ApplyOrchestrator: Parallel execution with ThreadPoolExecutor
    else serial execution
        ApplyOrchestrator->>ApplyOrchestrator: apply_serial(env, deployment_id, resources, filter, approve)

        loop for each provider
            ApplyOrchestrator->>Provider: set_environment(env_name)
            ApplyOrchestrator->>Provider: ensure_directories()

            ApplyOrchestrator->>StateManager: track_resource(deployment_id, env, provider, resource, APPLYING)
            StateManager-->>ApplyOrchestrator: tracked_resource

            ApplyOrchestrator->>EventManager: emit_event(RESOURCE_APPLYING, env, resource_data)

            ApplyOrchestrator->>SecretManager: export_for_terraform(secrets_file, tf_vars)
            SecretManager-->>ApplyOrchestrator: secrets exported

            loop for each runner (terraform, ansible, etc.)
                ApplyOrchestrator->>Provider: generate_{tool}(resources)
                Provider-->>ApplyOrchestrator: config generated

                ApplyOrchestrator->>Runner: run(provider, "apply", auto_approve)
                Runner-->>ApplyOrchestrator: runner_result
            end

            ApplyOrchestrator->>StateManager: update_resource_state(resource_id, DEPLOYED)
            ApplyOrchestrator->>EventManager: emit_event(RESOURCE_DEPLOYED, env, resource_data)
        end
    end

    ApplyOrchestrator->>StateManager: update_deployment_status(deployment_id, COMPLETED)
    ApplyOrchestrator->>EventManager: emit_event(AFTER_APPLY, env, results)

    ApplyOrchestrator-->>Orchestrator: results
    Orchestrator-->>CLI: results
    CLI-->>User: apply output displayed
```

### Rollback Workflow

```mermaid
sequenceDiagram
    actor User
    participant CLI
    participant Orchestrator
    participant RollbackOrchestrator
    participant StateManager
    participant ApplyOrchestrator
    participant ConfigManager
    participant Provider
    participant Runner

    User->>CLI: infra rollback --deployment-id 123
    CLI->>Orchestrator: rollback(deployment_id, auto_approve, confirm_callback)
    Orchestrator->>RollbackOrchestrator: rollback(deployment_id, auto_approve, confirm_callback)

    RollbackOrchestrator->>StateManager: get_deployment_by_id(deployment_id)
    StateManager-->>RollbackOrchestrator: deployment (with rollback_data)

    alt not auto_approve
        RollbackOrchestrator->>User: Display rollback details and prompt
        User-->>RollbackOrchestrator: confirm (yes/no)

        alt user declined
            RollbackOrchestrator-->>CLI: cancelled
            CLI-->>User: Rollback cancelled
        end
    end

    Note over RollbackOrchestrator: Extract environment and resources from rollback_data

    RollbackOrchestrator->>StateManager: create_deployment(env, "apply", user, False, rollback_metadata)
    StateManager-->>RollbackOrchestrator: rollback_deployment_id

    RollbackOrchestrator->>User: Warning: ensure git repo is at correct state

    RollbackOrchestrator->>ApplyOrchestrator: apply(env_name, None, auto_approve=True, parallel=False, max_workers=4)

    Note over ApplyOrchestrator: Standard apply workflow executes
    ApplyOrchestrator->>ConfigManager: load_resources(env_name)

    loop for each provider
        ApplyOrchestrator->>Provider: set_environment(env_name)
        ApplyOrchestrator->>Provider: generate_{tool}(resources)
        ApplyOrchestrator->>Runner: run(provider, "apply", True)
    end

    ApplyOrchestrator-->>RollbackOrchestrator: results

    RollbackOrchestrator->>StateManager: update_deployment_status(rollback_deployment_id, COMPLETED)

    RollbackOrchestrator-->>Orchestrator: results
    Orchestrator-->>CLI: results
    CLI-->>User: Rollback completed successfully
```

## Validation and Checks

- Use `infra validate --env <env> --check-api --check-refs` before workflows.
- Check state updates with `infra history`/`infra status`.
- Review event emissions (notifications/logs) to ensure hooks fire.

## Examples

- **Dependency grouping concept:**
  ```python
  resources_by_provider = group_resources(resources)
  for provider_name, items in resources_by_provider.items():
      provider = providers[provider_name]
      provider.generate_terraform(items)
      deployment_executor.execute(provider_name, items)
  ```
- **Event emission concept:**
  ```python
  event_manager.emit_event(EventType.BEFORE_APPLY, environment=env, data={...})
  ```

## Related Documentation

- [Infrastructure Architecture](ARCHITECTURE.md)
- [Pluggable Runners](pluggable-runners.md)
- [Architecture Overview](overview.md)
- [State Management](state-management.md)
- [Notifications Guide](../configuration/notifications.md)

## Troubleshooting

- **Symptom:** Providers not executed. **Fix:** Ensure provider registration and resource grouping; check resource `provider` fields.
- **Symptom:** Events/notifications missing. **Fix:** Verify subscribers are registered; run with higher log level.
- **Symptom:** State not updated. **Fix:** Confirm database backend connectivity and that workflow calls StateManager methods.

---

Last updated: 2025-12-02


---
[Back to Table of Contents](../TABLE_OF_CONTENTS.md)
