# Policy Configuration Guide

## Overview

InfraFoundry’s policy engine enforces rules before deployment. Policies can block (`error`) or warn (`warning`) based on resource limits, naming, required tags, or allowed providers.

## Audience and Prerequisites

- **Audience:** Operators and platform teams defining guardrails across environments.
- **Prereqs:** Config repo access, policy YAML under `policies/`, and familiarity with target environments/providers.

## When to Use This

- Enforcing naming conventions or tag requirements.
- Limiting resource sizes or restricting providers per environment.
- Adding pre-deployment checks that align with compliance or platform standards.

## Quick Start

1. Create `policies/default.yaml` (or any file under `policies/`):
   ```yaml
   policies:
     - name: strict-naming
       type: naming_convention
       rules:
         patterns:
           "*": "^[a-z0-9]+(-[a-z0-9]+)*$"
     - name: prod-limits
       type: resource_limit
       level: error
       environments: [prod]
       rules:
         limits:
           max_cpu: 16
           max_memory_mb: 32768
   ```
2. Check policies:
   ```bash
   foundry infra plan --env dev --enforce-policies
   foundry infra plan --env prod --enforce-policies
   ```

## Configuration Details

- **Location:** `policies/*.yaml` in the config repo. Multiple files allowed (e.g., `naming.yaml`, `security.yaml`).
- **Schema:**
  ```yaml
  policies:
    - name: unique-id            # required
      description: "..."         # optional
      type: <policy_type>        # required
      level: <warning|error>     # default: warning
      enabled: true              # default: true
      environments: [prod]       # optional filter
      rules: {...}               # required per type
  ```
- **Supported types:**
  - `resource_limit`: `rules.limits.max_cpu`, `rules.limits.max_memory_mb`.
  - `naming_convention`: `rules.patterns` map (`*` or `provider:type` → regex).
  - `required_tags`: `rules.tags` list of required tags.
  - `allowed_providers`: `rules.allowed` list.
- **Environment scoping:** `environments` restricts a policy to specific envs; omit to apply globally.

## Validation and Checks

- Run `foundry policy list` to list available policies.
- Run `foundry infra plan --env <env> --enforce-policies` to enforce policies during planning (blocks on violations).
- Combine with CI to block merges when policies fail.

## Examples

- **Required tags:**
  ```yaml
  - name: audit-tags
    type: required_tags
    level: warning
    rules:
      tags:
        - managed-by-infrafoundry
        - cost-center-required
  ```
- **Restrict providers in dev:**
  ```yaml
  - name: no-k8s-in-dev
    type: allowed_providers
    level: error
    environments: [dev]
    rules:
      allowed:
        - proxmox
        - opnsense
  ```

## Related Documentation

- [Validation and Pre-Flight Checks](../usage/validation.md)
- [Configuration Guide](overview.md)
- [Separate Config Repo](separate-config-repo.md)

## Troubleshooting

- **Symptom:** Policies not applied. **Fix:** Ensure files live under `policies/`, have `policies:` root, and `enabled: true`.
- **Symptom:** Unexpected blocks. **Fix:** Check `environments` filters and regex patterns; lower severity to `warning` if needed.
- **Symptom:** Regex not matching. **Fix:** Validate patterns externally; ensure selectors use `provider:type` or `*`.

---

Last updated: 2025-12-23 14:19 GMT


---
[Back to Table of Contents](../index.md)
