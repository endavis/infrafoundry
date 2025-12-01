# YAML-Only Configuration

## Overview

InfraFoundry uses **pure YAML** for all environment, resource, and credential configuration. The framework converts YAML to the required Terraform/Ansible inputs automatically—no hand-written HCL needed.

## Audience and Prerequisites

- **Audience:** Config repo maintainers and operators defining environments/resources.
- **Prereqs:** Config repo available, `sops`/`age` for secrets, `uv run infra` installed, and provider credentials ready.

## When to Use This

- Migrating from mixed YAML+HCL to a single YAML workflow.
- Creating new environments or services without writing HCL.
- Applying per-provider SSH or credential overrides in YAML.

## Quick Start

1. Add or update `envs/{env}/settings.yaml` with SSH and provider settings.
2. Define resources in YAML (`envs/{env}/resources/*.yaml` or provider folders).
3. Encrypt secrets with SOPS/age as needed.
4. Generate and validate:
   ```bash
   infra validate --env dev
   infra plan --env dev
   ```

## Configuration Details

- **Settings location:** `envs/{env}/settings.yaml` holds environment metadata, SSH, and `provider_settings`. Per-provider SSH overrides live under `provider_ssh`.
- **Resource layouts:** Use resource-centric (`envs/{env}/resources/*.yaml`) for multi-provider services, or provider-centric (`envs/{env}/{provider}/*.yaml`) when grouping by provider. Mixing is supported.
- **Auto-generated tfvars:** Terraform variables are rendered from `settings.yaml` into `generated/{env}/terraform/{provider}/terraform.tfvars`.
- **Secrets:** Store sensitive values in `settings.yaml` and encrypt with SOPS/age; InfraFoundry decrypts during generate/apply.

## Validation and Checks

- Run `infra validate --env <env> --check-api --check-refs` to confirm YAML structure, provider discovery, connectivity, and referenced templates/networks/aliases.
- Inspect generated Terraform inputs under `generated/{env}/terraform/{provider}/terraform.tfvars` to confirm values and SSH overrides.

## Examples

- **Global SSH and provider settings (`settings.yaml`):**
  ```yaml
  name: test
  description: Test environment
  ssh:
    user: endavis
    key_path: /home/endavis/.ssh/id_ed25519
  provider_settings:
    proxmox:
      api_url: https://pve01.example.com:8006
      api_token: your-api-token
      node: pve01
      storage: local-lvm
  ```
- **Per-provider SSH overrides:**
  ```yaml
  provider_ssh:
    proxmox:
      user: proxmox-admin
      key_path: /secure/keys/proxmox_prod
      port: 2222
    opnsense:
      user: opnsense-admin
      key_path: /secure/keys/opnsense_prod
  ```
- **Resource-centric service file:**
  ```yaml
  resources:
    - provider: proxmox
      type: vm
      name: web-server-01
      config:
        target_node: pve1
        clone: ubuntu-22-04-template
        network:
          bridge: vmbr0
          tag: 10
        ipconfig: ip=dhcp
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

## Related Documentation

- [Configuration Guide](overview.md)
- [SSH Authentication](../guides/ssh-authentication.md)
- [Per-Environment Credentials](per-environment-credentials.md)
- [Separate Config Repo](separate-config-repo.md)

## Troubleshooting

- **Symptom:** Generated `terraform.tfvars` missing values. **Fix:** Ensure fields exist in `settings.yaml`; rerun `infra plan`.
- **Symptom:** Providers not discovered. **Fix:** Confirm resource files include `provider` keys and are placed under `resources/` or provider directories.
- **Symptom:** SSH fails during Proxmox operations. **Fix:** Verify `ssh` or `provider_ssh` entries and that keys are accessible; re-run `infra validate --check-api`.

---

Last updated: 2025-11-29 14:19 GMT


---
[Back to Table of Contents](../TABLE_OF_CONTENTS.md)
