# Setting Up Your InfraFoundry Configuration

## Overview

This guide helps you stand up InfraFoundry with Proxmox and OPNsense, covering both automated and manual setup paths so you can start planning and applying infrastructure.

## Audience and Prerequisites

- **Audience:** New InfraFoundry users configuring their first environment; operators onboarding additional environments.
- **Prereqs:** `git`, `uv`, `terraform`, `ansible`, `sops`, `age`, provider access to Proxmox and OPNsense, and a config repo location (`--config-dir` or `INFRAFOUNDRY_CONFIG_REPO`).

## When to Use This

- First-time setup for a fresh environment.
- Recreating a config workspace on a new machine.
- Switching from manual to scripted setup.

## Quick Start

1. Install dependencies (installs `uv`, `doit`, Terraform, Ansible, SOPS, age):
   ```bash
   ./scripts/setup-dependencies.sh
   ```
2. Run the interactive config wizard:
   ```bash
   ./scripts/setup-config.sh
   ```
3. Point InfraFoundry to your config repo if it is not in `./envs`:
   ```bash
   export INFRAFOUNDRY_CONFIG_REPO=/path/to/my-infra-config
   ```
4. Validate connectivity and structure:
   ```bash
   foundry config doctor --deep
   foundry infra doctor --env dev
   ```

## Configuration Details

- **Config repo location:** Use `--config-dir` or `INFRAFOUNDRY_CONFIG_REPO`; defaults to `./envs`.
- **Example layout (recommended separate repo):**
  ```bash
  cp -r example-config ../my-infra-config
  cd ../my-infra-config
  git init && git add . && git commit -m "Initial configuration"
  export INFRAFOUNDRY_CONFIG_REPO=$(pwd)
  ```
- **Information to gather before manual setup:**
  - **Proxmox:** API URL (`https://<ip>:8006/api2/json`), token ID/secret, node names, storage pool, bridge, VM template.
  - **OPNsense:** Web UI URL, API key/secret.
  - **Network:** CIDR, gateway, DNS servers, domain.
- **Environment creation (manual):**
  ```bash
  mkdir -p envs/dev/resources
  cp example-config/envs/dev/settings.yaml envs/dev/settings.yaml
  # Add resource files under envs/dev/resources/*.yaml
  ```

## Validation and Checks

- Run `foundry config doctor` after populating settings and resources.
- Run `foundry infra doctor --env <env>` before first apply to catch connectivity and reference issues.
- Review generated outputs in `generated/{env}/terraform` and `generated/{env}/ansible` when planning.

## Examples

- **Plan after setup:**
  ```bash
  foundry infra plan --env dev
  ```
- **Apply a newly configured environment:**
  ```bash
  foundry infra apply --env dev
  ```
- **Destroy if you need to reset:**
  ```bash
  foundry infra destroy --env dev
  ```

## Related Documentation

- [Configuration](../configuration/overview.md)
- [YAML-Only Config](../configuration/yaml-only-config.md)
- [Per-Environment Credentials](../configuration/per-environment-credentials.md)
- [Direnv Setup](direnv.md)
- [Validation and Pre-Flight Checks](../usage/validation.md)

## Troubleshooting

- **Symptom:** Missing dependencies. **Fix:** Re-run `./scripts/setup-dependencies.sh`; confirm `uv` is on `PATH`.
- **Symptom:** Cannot reach Proxmox/OPNsense. **Fix:** Verify API URLs, tokens/keys, and network access; rerun `foundry infra doctor --env <env>`.
- **Symptom:** Configs not found. **Fix:** Ensure `INFRAFOUNDRY_CONFIG_REPO` or `--config-dir` points to your repo and `envs/{env}` exists.

---

Last updated: 2025-12-23 14:12 GMT


---
[Back to Table of Contents](../index.md)
