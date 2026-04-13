# Validation and Pre-Flight Checks

## Overview

InfraFoundry provides a three-tier validation system to catch configuration, reference, and connectivity issues **before** `foundry infra plan` or `foundry infra apply`, keeping deployments safe and predictable.

## Audience and Prerequisites

- **Audience:** Operators and CI pipelines running plan/apply workflows.
- **Prerequisites:** Config repo available, `foundry` installed via `uv`, provider credentials and network access for targeted environments.

## When to Use This

- Before any plan/apply, especially for production changes.
- After editing settings, resources, or secrets to ensure structural integrity.
- In CI to block merges when validation fails.

## Three-Tier Doctor System

InfraFoundry validation is organized into three levels, each checking a different scope:

| Level | Command | What It Checks |
|-------|---------|----------------|
| **System** | `foundry doctor` | Binary dependencies (Terraform, OpenTofu, Ansible, SOPS, Age) |
| **Config** | `foundry config doctor [--deep]` | Config repo structure, environments, state backend, SOPS keys, state/filesystem consistency, blueprint validation |
| **Infrastructure** | `foundry infra doctor --env <env>` | Provider API connectivity, nodes/hosts, storage pools, network bridges, templates, resource IDs, MAC conflicts |

## Quick Start

```bash
# Check system dependencies
foundry doctor

# Check config repo health
foundry config doctor --deep

# Validate against provider APIs
foundry infra doctor --env dev
foundry infra doctor --env dev --resource vm-01 --resource vm-02
foundry infra doctor --env dev --verbose
```

## Additional Validation Commands

Beyond the doctor commands, InfraFoundry offers additional validation tools:

- **`foundry infra test --env <env>`** -- Run infrastructure tests against configurations (duplicate names, missing references, configuration problems).
- **`foundry infra security --env <env>`** -- Scan generated Terraform/Ansible for security issues using Checkov.
- **`foundry infra analyze dependencies --env <env>`** -- Verify dependency graph is acyclic and references resolve.

## Examples

- **Pre-deployment validation:**
  ```bash
  foundry config doctor --deep
  foundry infra doctor --env prod
  foundry infra test --env prod
  ```
- **CI usage (GitHub Actions excerpt):**
  ```yaml
  jobs:
    validate:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - run: foundry config doctor --deep
        - run: foundry infra doctor --env prod
        - run: foundry infra test --env prod
  ```

## Related Documentation

- [CLI Reference](cli-reference.md)
- [Settings File Structure](../configuration/settings-file-structure.md)
- [Per-Environment Credentials](../configuration/per-environment-credentials.md)
- [State Management](../architecture/state-management.md)

## Troubleshooting

- **Symptom:** Missing templates/networks in doctor output. **Fix:** Create the resource in the provider or update the configuration reference; rerun `foundry infra doctor --env <env>`.
- **Symptom:** Doctor reports API failures. **Fix:** Verify endpoints, tokens, kubeconfig, and network reachability; test with provider CLIs.
- **Symptom:** Unknown resource/provider. **Fix:** Confirm resource type spelling and provider availability in the current framework version.

---

Last updated: 2026-04-13 GMT


---
[Back to Table of Contents](../index.md)
