# OpenTofu Runner Guide

## Overview

The OpenTofu runner is a drop-in alternative to the Terraform runner. OpenTofu is an open-source fork of Terraform with a fully compatible CLI, so the same `.tf` files, state format, and subcommands (`init`, `plan`, `apply`, `destroy`, `show`, `validate`, `version`) work identically.

## Audience and Prerequisites

- **Audience:** Operators who prefer or require OpenTofu instead of Terraform.
- **Prereqs:** OpenTofu (`tofu`) installed, config repo available, provider credentials/SSH configured.

## When to Use This

- You need an open-source-licensed IaC tool.
- Your organisation has standardised on OpenTofu.
- You want the same InfraFoundry workflow but with the `tofu` binary.

## Quick Start

1. Install OpenTofu:
   ```bash
   doit install_opentofu
   ```

2. Configure your environment to use OpenTofu in `envs/{env}/settings.yaml`:
   ```yaml
   iac_tool: opentofu
   ```

   Or set the environment variable:
   ```bash
   export INFRAFOUNDRY_IAC_TOOL=opentofu
   ```

3. Run as usual:
   ```bash
   infra plan --env dev
   infra apply --env dev
   ```

## Configuration Details

- **Tool selection:** Set `iac_tool: opentofu` in your environment's `settings.yaml` or use `INFRAFOUNDRY_IAC_TOOL=opentofu`.
- **Default:** `terraform` (backward compatible).
- **Generated files:** Output goes to `generated/{env}/terraform/{provider}/` regardless of tool selection. The `.tf` file format is shared between Terraform and OpenTofu.
- **State location:** `generated/{env}/terraform/{provider}/.terraform/terraform.tfstate` (same as Terraform; OpenTofu uses the same state format).
- **Settings/secrets:** Identical to Terraform; `settings.yaml` maps to `terraform.tfvars`.

## Architecture

`OpenTofuRunner` extends `TerraformRunner` and overrides only the `tool_name` property (returns `"tofu"` instead of `"terraform"`). All other behaviour - initialisation, planning, applying, state tracking, drift detection - is inherited.

```
BaseRunner
  |-- TerraformRunner (tool_name = "terraform")
        |-- OpenTofuRunner (tool_name = "tofu")
```

## Examples

- **YAML config with OpenTofu:**
  ```yaml
  # envs/dev/settings.yaml
  iac_tool: opentofu
  providers:
    - proxmox
  ```

- **Run OpenTofu manually for debugging:**
  ```bash
  cd generated/dev/terraform/proxmox
  tofu plan
  ```

## Related Documentation

- [Terraform Runner](terraform.md)
- [Runner Execution Overview](overview.md)
- [Configuration Guide](../configuration/overview.md)

## Troubleshooting

- **Symptom:** `tofu` command not found. **Fix:** Install OpenTofu with `doit install_opentofu` or from [opentofu.org](https://opentofu.org/docs/intro/install/).
- **Symptom:** Drift detection still uses Terraform. **Fix:** Ensure `iac_tool: opentofu` is set in the environment's `settings.yaml`.
- **Symptom:** State file conflicts. **Fix:** Both tools use `terraform.tfstate`; do not switch tools on an existing environment without migrating state.

---

Last updated: 2026-02-08

---
[Back to Table of Contents](../index.md)
