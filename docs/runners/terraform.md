# Terraform Runner Guide

## Overview

The Terraform runner provisions infrastructure from YAML by rendering `.tf` files and executing `terraform init/plan/apply`. Provider credentials and settings are passed to Terraform via `TF_VAR_*` environment variables — no `.tfvars` files are written to disk.

## Audience and Prerequisites

- **Audience:** Operators provisioning with InfraFoundry’s Terraform backend.
- **Prereqs:** Terraform installed, config repo available, provider credentials/SSH configured.

## When to Use This

- Provisioning compute/network/storage resources.
- Inspecting generated Terraform for debugging.
- Configuring state backends and provider options via YAML.

## Quick Start

```bash
foundry infra plan --env dev
foundry infra apply --env dev
```

## Configuration Details

- **Resource definitions:** YAML resources map to provider Terraform resources; no direct HCL authoring.
- **Settings/secrets:** Provider credentials from `settings.yaml` are mapped to `TF_VAR_*` environment variables via each provider's `_CREDENTIAL_ENV_MAPPING`. The `TerraformRunner._prepare_environment()` method calls `provider.get_terraform_env_vars()` to build the full set of `TF_VAR_*` variables. No `.tfvars` files are generated.
- **State location:** `generated/{env}/terraform/{provider}/.terraform/terraform.tfstate` (remote backends configurable via env vars/provider settings).
- **Customization:** Provider-specific options (e.g., cloud-init snippets) are surfaced via YAML fields; raw HCL injection is intentionally limited to preserve consistency.

## Validation and Checks

- Validate configs and references before running:
  ```bash
  foundry infra doctor --env dev
  ```
- Inspect generated files for debugging:
  ```bash
  cat generated/dev/terraform/proxmox/main.tf
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

- **Symptom:** Terraform errors on apply. **Fix:** Inspect generated `.tf` files; rerun `foundry infra doctor --env <env>`. Check that provider credentials in `settings.yaml` are correct — they are passed as `TF_VAR_*` env vars.
- **Symptom:** State conflicts. **Fix:** Configure remote backend with locking (e.g., S3 + DynamoDB) and avoid sharing local state dirs.
- **Symptom:** Missing credentials. **Fix:** Ensure `settings.yaml` contains provider credentials and is decrypted. Credentials are mapped to `TF_VAR_*` env vars automatically via each provider's `_CREDENTIAL_ENV_MAPPING`.

---

Last updated: 2026-03-18


---
[Back to Table of Contents](../index.md)
