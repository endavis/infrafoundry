# Runner Execution Overview

## Overview

InfraFoundry executes runners (Terraform, Ansible, PyInfra) in priority order to provision, configure, and deploy. Defaults reflect provisioning → system config → app deployment.

## Audience and Prerequisites

- **Audience:** Operators and contributors tuning runner order or usage.
- **Prereqs:** `settings.yaml` access and awareness of runner applicability per resource.

## When to Use This

- Understanding how runners are sequenced.
- Changing runner priorities for bootstrapping needs.
- Mapping resource fields to runner selection.

## Quick Start

Default order: Terraform (0) → Ansible (50) → PyInfra (50; after Ansible by registration).

Customize priorities in `envs/{env}/settings.yaml`:
```yaml
runner_priorities:
  pyinfra: 40
  ansible: 60
```

## Configuration Details

- **Execution order:** Ascending priority; ties resolved by registration order (Ansible before PyInfra).
- **Defaults:** Terraform 0, Ansible 50, PyInfra 50.
- **Runner applicability by resource fields:**
  - Terraform: resource provisioning (VMs, networks, etc.).
  - Ansible: `ansible_roles`, `ansible_tasks`, `ansible_vars`.
  - PyInfra: `pyinfra_ops`, `pyinfra_deploy_funcs`.
- **Generated outputs:** `generated/{env}/{runner}/{provider}/`.

## Validation and Checks

- Confirm priorities with `runner_priorities` in `settings.yaml`.
- Inspect generated runner outputs for order and content.
- Validate resources before run: `infra validate --env <env> --check-refs`.

## Examples

- **Default order:** Terraform → Ansible → PyInfra.
- **Run PyInfra before Ansible:**
  ```yaml
  runner_priorities:
    pyinfra: 40
    ansible: 60
  ```
- **Mixed resource:** A VM with both Ansible roles and PyInfra ops triggers all applicable runners in priority order.

## Related Documentation

- [Pluggable Runner System](../architecture/pluggable-runners.md)
- [Configuration Guide](../configuration/overview.md)
- [Terraform Runner](terraform.md)
- [Ansible Runner](ansible.md)
- [PyInfra Runner](pyinfra.md)

## Troubleshooting

- **Symptom:** Runner executes unexpectedly. **Fix:** Check resource fields that trigger runner applicability and `runner_priorities`.
- **Symptom:** Order incorrect. **Fix:** Adjust priorities; ensure numeric values differ if order must change.
- **Symptom:** Outputs missing. **Fix:** Verify resources trigger runner; check `generated/{env}/{runner}/{provider}` for rendered files.

---

Last updated: 2025-11-29 14:27 GMT


---
[Back to Table of Contents](../TABLE_OF_CONTENTS.md)
