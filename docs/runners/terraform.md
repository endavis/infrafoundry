# Terraform Runner Guide

## Overview

The Terraform runner provisions infrastructure from YAML by rendering `.tf` files, mapping settings/secrets into `terraform.tfvars`, and executing `terraform init/plan/apply`.

## Audience and Prerequisites

- **Audience:** Operators provisioning with InfraFoundry’s Terraform backend.
- **Prereqs:** Terraform installed, config repo available, provider credentials/SSH configured.

## When to Use This

- Provisioning compute/network/storage resources.
- Inspecting generated Terraform for debugging.
- Configuring state backends and provider options via YAML.

## Quick Start

```bash
infra plan --env dev
infra apply --env dev
```

## Configuration Details

- **Resource definitions:** YAML resources map to provider Terraform resources; no direct HCL authoring.
- **Settings/secrets:** `settings.yaml` → `terraform.tfvars` in `generated/{env}/terraform/{provider}/`.
- **State location:** `generated/{env}/terraform/{provider}/.terraform/terraform.tfstate` (remote backends configurable via env vars/provider settings).
- **Customization:** Provider-specific options (e.g., cloud-init snippets) are surfaced via YAML fields; raw HCL injection is intentionally limited to preserve consistency.

## Validation and Checks

- Validate configs and references before running:
  ```bash
  infra validate --env dev --check-api --check-refs
  ```
- Inspect generated files for debugging:
  ```bash
  cat generated/dev/terraform/proxmox/main.tf
  cat generated/dev/terraform/proxmox/terraform.tfvars
  ```

## Examples

- **YAML VM definition (maps to Terraform resource):**
  ```yaml
  resources:
    - provider: proxmox
      type: vm
      name: db-prod-01
      config:
        node: pve01
        cores: 4
        memory: 16384
        ipconfig: ip=10.0.0.5/24,gw=10.0.0.1
  ```
- **Run Terraform manually for debugging:**
  ```bash
  cd generated/dev/terraform/proxmox
  terraform plan
  ```

## Related Documentation

- [OpenTofu Runner](opentofu.md) - Open-source alternative using the same `.tf` format
- [Runner Execution Overview](overview.md)
- [Configuration Guide](../configuration/overview.md)
- [State Management](../architecture/state-management.md)
- [SSH Authentication](../guides/ssh-authentication.md)

## Troubleshooting

- **Symptom:** Terraform errors on apply. **Fix:** Inspect generated `.tf`/`terraform.tfvars`; rerun `infra validate --check-api --check-refs`.
- **Symptom:** State conflicts. **Fix:** Configure remote backend with locking (e.g., S3 + DynamoDB) and avoid sharing local state dirs.
- **Symptom:** Missing credentials. **Fix:** Ensure `settings.yaml` contains provider credentials and is decrypted; confirm env vars if using remote backend.

---

Last updated: 2025-12-23 14:27 GMT


---
[Back to Table of Contents](../index.md)
