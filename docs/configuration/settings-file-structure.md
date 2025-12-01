# Settings File Structure

## Overview

Each environment uses a single SOPS-encrypted `settings.yaml` to define metadata, SSH defaults, provider credentials, and overrides. InfraFoundry renders Terraform/Ansible inputs from this YAML—no HCL required.

## Audience and Prerequisites

- **Audience:** Config repo maintainers defining environment settings and secrets.
- **Prereqs:** Config repo with `envs/{env}`, `sops` + `age` installed, and provider credentials for targeted platforms.

## When to Use This

- Creating or updating environment settings and credentials.
- Adding provider-specific SSH overrides or defaults.
- Auditing the required fields for `settings.yaml`.

## Quick Start

1. Create `envs/{env}/settings.yaml` and add metadata, SSH, and provider settings.
2. Encrypt with SOPS/age:
   ```bash
   sops --encrypt --in-place envs/dev/settings.yaml
   ```
3. Validate and plan:
   ```bash
   infra validate --env dev --check-api
   infra plan --env dev
   ```

## Configuration Details

- **File location:** `envs/{env}/settings.yaml` (encrypted with SOPS/age).
- **Key sections:**
  - `name`, `description`, optional `variables` (for templates).
  - `ssh` (global SSH defaults) and `provider_ssh` (per-provider overrides).
  - `provider_settings` per provider (credentials, endpoints, defaults).
- **Example structure:**
  ```yaml
  name: prod
  description: Production environment
  variables:
    datacenter: dc1
    domain: example.com

  ssh:
    user: automation
    key_path: /home/automation/.ssh/id_ed25519

  provider_ssh:
    proxmox:
      user: root
      key_path: /secure/keys/proxmox_ed25519
      port: 2222

  provider_settings:
    proxmox:
      api_url: https://pve01.example.com:8006
      api_token: pve-token-id=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
      node: pve01
      storage: local-zfs
    opnsense:
      api_url: https://fw.example.com
      api_key: xxxxxxxxxxxxxxxxxxxx
      api_secret: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    kubernetes:
      kubeconfig_path: ~/.kube/config
      namespace: infra
  ```
- **Schema hints:**
  - `ssh.user`/`key_path`/`port` (optional, defaults to current user and port 22).
  - `provider_ssh.<provider>` overrides global SSH.
  - `provider_settings.<provider>` holds credentials/endpoints; fields vary by provider.
- **Generated outputs:** Values populate `generated/{env}/terraform/{provider}/terraform.tfvars` and Ansible vars automatically.

## Validation and Checks

- Run `infra validate --env <env> --check-api` to confirm structure and credentials.
- Inspect generated tfvars to verify SSH overrides and provider settings:
  ```bash
  cat generated/dev/terraform/proxmox/terraform.tfvars
  ```
- Ensure `settings.yaml` is encrypted and keys are git-ignored.

## Examples

- **Dev settings with minimal fields:**
  ```yaml
  name: dev
  description: Development environment
  provider_settings:
    proxmox:
      api_url: https://pve-dev.example.com:8006
      api_token: pve-dev-token
  ```
- **Per-provider SSH override:**
  ```yaml
  provider_ssh:
    opnsense:
      user: opnsense-admin
      key_path: /secure/keys/opnsense_prod
      port: 22
  ```
- **Kubernetes settings:**
  ```yaml
  provider_settings:
    kubernetes:
      kubeconfig_path: ~/.kube/config
      namespace: platform
  ```

## Related Documentation

- [Configuration Guide](overview.md)
- [YAML-Only Configuration](yaml-only-config.md)
- [Per-Environment Credentials](per-environment-credentials.md)
- [SSH Authentication](../guides/ssh-authentication.md)

## Troubleshooting

- **Symptom:** Missing values in generated tfvars. **Fix:** Ensure fields exist in `settings.yaml` and rerun `infra plan`.
- **Symptom:** SSH fails during Proxmox operations. **Fix:** Verify `ssh`/`provider_ssh` entries and key paths; re-validate with `--check-api`.
- **Symptom:** Secrets exposed in git. **Fix:** Encrypt `settings.yaml` with SOPS/age and confirm ignore rules include keys.

---

Last updated: 2025-11-29 14:19 GMT


---
[Back to Table of Contents](../TABLE_OF_CONTENTS.md)
