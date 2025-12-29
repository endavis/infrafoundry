# InfraFoundry Architecture Overview

## Overview

InfraFoundry separates code generation from execution: YAML configs are rendered into Terraform/Ansible, then optionally orchestrated. Providers are pluggable, orchestration is event-driven, and configs live outside the framework.

## Audience and Prerequisites

- **Audience:** Engineers extending or operating InfraFoundry.
- **Prereqs:** Familiarity with Terraform/Ansible basics and access to the config repo.

## When to Use This

- Understanding high-level data flow and responsibilities.
- Explaining how plan/apply/destroy map to generation vs execution.
- Onboarding contributors to the architecture.

## Quick Start

1. Generate only:
   ```bash
   infra plan --env dev
   ```
2. Generate + execute:
   ```bash
   infra apply --env dev
   ```
3. Destroy:
   ```bash
   infra destroy --env dev
   ```

## Architecture Details

- **Code generation layer:** Providers (Proxmox/OPNsense/Kubernetes) implement `ProviderBase`; Jinja2 templates emit Terraform/Ansible; ConfigManager loads/validates YAML; SecretManager decrypts SOPS and exports to tools.
- **Orchestration layer:** Orchestrator coordinates multi-provider runs; CLI (Click) drives commands; StateManager tracks deployments; Event system powers notifications/integrations; Policy engine enforces guardrails.
- **Data flow:**
  `YAML configs → ConfigManager → Providers → Jinja2 templates → generated/{env}/{terraform|ansible}/{provider} → (optional) terraform init/apply + ansible-playbook → infrastructure`

  ```mermaid
  graph LR
      A[YAML Configs] -->|Load & Validate| B[ConfigManager]
      B -->|Group Resources| C[Providers]
      C -->|Render| D[Jinja2 Templates]
      D -->|Generate| E[Generated Artifacts]
      E -->|Execute| F[Runners]
      F -->|Apply| G[Infrastructure]

      subgraph "Framework"
      B
      C
      D
      end

      subgraph "Artifacts"
      E
      end

      subgraph "Execution"
      F
      end
  ```

- **Key principles:** Generate before execute; provider plugins; tool-agnostic outputs; separate framework and config repos.

## Validation and Checks

- `infra validate --env <env> --check-api --check-refs` before plan/apply.
- Inspect generated Terraform/Ansible under `generated/{env}/...` to verify outputs before execution.

## Examples

- **Review without applying:** `infra plan --env dev --dry-run` (validate only).
- **Full run:** `infra apply --env prod` (generate + terraform + ansible + state tracking).
- **Remove:** `infra destroy --env prod` (tears down resources via Terraform/Ansible).

## Related Documentation

- [Orchestrator Architecture](orchestrator-architecture.md)
- [Pluggable Runners](pluggable-runners.md)
- [Secrets Architecture](secrets-architecture.md)
- [Configuration Guide](../configuration/overview.md)
- [State Management](state-management.md)

## Troubleshooting

- **Symptom:** Generated files missing. **Fix:** Run `infra plan --env <env>` and ensure configs are present; check `generated/{env}`.
- **Symptom:** Execution fails after generation. **Fix:** Inspect generated Terraform/Ansible, rerun `infra validate --check-api --check-refs`, and address provider-specific errors.
- **Symptom:** Policies or events not triggered. **Fix:** Confirm event subscriptions and policy files are present; run with validation/policy checks to surface issues.

---

Last updated: 2025-12-23 14:27 GMT


---
[Back to Table of Contents](../index.md)
