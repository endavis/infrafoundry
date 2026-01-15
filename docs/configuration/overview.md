# InfraFoundry Configuration Guide

## Overview

InfraFoundry environments are defined entirely in YAML: `settings.yaml` for environment metadata/credentials and resource files organized by provider or service. Providers are auto-discovered from the resources you declare—no extra registration step required.

## Audience and Prerequisites

- **Audience:** Config repo maintainers and operators creating or updating environments.
- **Prereqs:** Config repo path (`--config-dir` or `INFRAFOUNDRY_CONFIG_REPO`), `sops`/`age` for secrets, `uv run infra` installed, and provider credentials.

## When to Use This

- Standing up new environments (dev/staging/prod) or services.
- Choosing between provider-centric and resource-centric layouts.
- Adding provider credentials, SSH settings, or shared variables.

## Quick Start

1. Create `envs/{env}/settings.yaml` with environment metadata, SSH (optional), and `provider_settings`.
2. Choose a layout:
   - Resource-centric: `envs/{env}/resources/*.yaml` (recommended for multi-provider services).
   - Provider-centric: `envs/{env}/{provider}/*.yaml`.
3. Encrypt secrets in `settings.yaml` with SOPS/age.
4. Validate and plan:
   ```bash
   infra validate --env dev --check-api --check-refs
   infra plan --env dev
   ```

## Configuration Details

- **Environment file:** `envs/{env}/settings.yaml`
  - Metadata: `name`, `description`, optional `variables`.
  - SSH: `ssh` (global) and `provider_ssh` (overrides).
  - Credentials/endpoints: `provider_settings` per provider.
- **Resource layouts:**
  - **Provider-centric:** `envs/{env}/{provider}/{resource_type}.yaml`; scalable to multiple files per type (e.g., `vm-web.yaml`, `vm-db.yaml`).
  - **Resource-centric:** `envs/{env}/resources/*.yaml` combining multiple providers per service/app.
  - Mixing both is supported; InfraFoundry groups by `provider` and `type`.
- **Generated artifacts:** Terraform vars land in `generated/{env}/terraform/{provider}/terraform.tfvars`; Ansible content under `generated/{env}/ansible/{provider}/`.
- **Secrets:** Keep sensitive values in `settings.yaml` and encrypt with SOPS/age. InfraFoundry decrypts during validate/plan/apply.

## Validation and Checks

- Run `infra validate --env <env>` for structure and type checks; add `--check-api --check-refs` to verify connectivity and referenced resources.
- Confirm provider discovery by checking per-provider sections in validation output.
- Inspect generated tfvars under `generated/{env}/terraform/{provider}/` to confirm SSH overrides and credentials.

## Examples

- **Minimal `settings.yaml`:**
  ```yaml
  name: dev
  description: Development environment
  ssh:
    user: your-username
    key_path: /path/to/ssh/key
  provider_settings:
    proxmox:
      api_url: https://pve01.example.com:8006
      api_token: your-api-token
      node: pve01
      storage: local-lvm
  ```
- **Provider-centric file (Proxmox VMs):**
  ```yaml
  # envs/dev/proxmox/vm.yaml
  vm:
    - name: web-server-01
      target_node: pve01
      clone: ubuntu-22-04-template
      cores: 2
      memory: 4096
  ```
- **Resource-centric service definition:**
  ```yaml
  # envs/prod/resources/web-server.yaml
  resources:
    - provider: proxmox
      type: vm
      name: web-server-01
      config:
        node: pve1
        cores: 4
        memory: 8192
        network:
          bridge: vmbr0
          vlan: 10
    - provider: opnsense
      type: firewall_rule
      name: allow-web-80
      config:
        action: pass
        interface: LAN
        protocol: tcp
        destination_port: 80
        destination: web-server-01
  ```
- **Secrets workflow:**
  ```bash
  infra secrets init
  infra secrets encrypt envs/dev/settings.yaml
  infra secrets decrypt envs/dev/settings.yaml
  ```

## Related Documentation

- [YAML-Only Configuration](yaml-only-config.md)
- [Separate Config Repo](separate-config-repo.md)
- [SSH Authentication](../guides/ssh-authentication.md)
- [Per-Environment Credentials](per-environment-credentials.md)
- [Validation and Pre-Flight Checks](../usage/validation.md)

## Troubleshooting

- **Symptom:** Providers not detected. **Fix:** Ensure resource files include `provider` keys and live under `resources/` or provider directories.
- **Symptom:** SSH operations fail in Proxmox. **Fix:** Verify `ssh`/`provider_ssh` entries and key paths; rerun `infra validate --check-api`.
- **Symptom:** Secrets not decrypted. **Fix:** Confirm SOPS/age keys are available and `settings.yaml` is encrypted with the expected rules.

---

Last updated: 2025-12-23 14:19 GMT


---
[Back to Table of Contents](../index.md)
