# SSH Authentication for Proxmox Operations

## Overview

InfraFoundry uses SSH for Proxmox tasks that lack API support (image extraction, `qm importdisk`). Configure SSH per environment/provider so Terraform provisioners work reliably.

## Audience and Prerequisites

- **Audience:** Operators running Proxmox plans/applies locally or in CI.
- **Prereqs:** Proxmox SSH access, `settings.yaml` configured, and optionally ssh-agent or CI-provided keys.

## When to Use This

- Importing images or performing Proxmox operations that require SSH.
- Differentiating SSH credentials across environments/providers.
- Running Proxmox workflows in CI where explicit key paths are needed.

## Quick Start

1. Set SSH in `envs/{env}/settings.yaml`:
   ```yaml
   ssh:
     user: automation
     key_path: /home/automation/.ssh/id_ed25519
   provider_ssh:
     proxmox:
       port: 2222
   ```
2. Run with validation:
   ```bash
   infra validate --env dev --check-api
   infra apply --env dev
   ```
3. CI: write the key to disk and set `TF_VAR_proxmox_ssh_key_path`.

## Configuration Details

- **Defaults:** Uses current user, ssh-agent or `~/.ssh/config`, port `22`.
- **Overrides:** `ssh` (global) and `provider_ssh.proxmox` (per-provider) in `settings.yaml`; InfraFoundry renders them into `terraform.tfvars`.
- **Authentication options:**
  - ssh-agent (recommended for local): `ssh-add ~/.ssh/id_ed25519`.
  - Explicit key path: set `TF_VAR_proxmox_ssh_key_path` or `provider_ssh.proxmox.key_path`.
  - SSH config: manage hosts in `~/.ssh/config`.
  - CI: store private key in pipeline secrets, write to `~/.ssh/proxmox_ci`, `chmod 600`, set `TF_VAR_proxmox_ssh_key_path`, and add host keys (`ssh-keyscan`).
- **Variables:** `proxmox_ssh_user`, `proxmox_ssh_key_path`, `proxmox_ssh_port` (defaults: `root`, `""` uses agent, `22`).

## Validation and Checks

- Test connectivity manually: `ssh -v root@pve1 "hostname"`.
- Run `infra validate --env <env> --check-api` to confirm SSH-based operations can proceed.
- Ensure keys are readable (`chmod 600`) and loaded into ssh-agent when used.

## Examples

- **Per-provider SSH overrides:**
  ```yaml
  provider_ssh:
    proxmox:
      user: proxmox-admin
      key_path: /secure/keys/proxmox_prod
      port: 2222
  ```
- **CI (GitHub Actions excerpt):**
  ```yaml
  - run: |
      mkdir -p ~/.ssh
      echo "${{ secrets.PROXMOX_SSH_KEY }}" > ~/.ssh/proxmox_ci
      chmod 600 ~/.ssh/proxmox_ci
      ssh-keyscan pve1 >> ~/.ssh/known_hosts
      echo "TF_VAR_proxmox_ssh_key_path=$HOME/.ssh/proxmox_ci" >> $GITHUB_ENV
      echo "TF_VAR_proxmox_ssh_user=root" >> $GITHUB_ENV
  ```
- **SSH config option:**
  ```ssh-config
  Host pve1 pve2
      User root
      IdentityFile ~/.ssh/id_ed25519
      Port 22
  ```

## Related Documentation

- [Configuration Guide](../configuration/overview.md)
- [YAML-Only Configuration](../configuration/yaml-only-config.md)
- [Per-Environment Credentials](../configuration/per-environment-credentials.md)
- [Validation and Pre-Flight Checks](../usage/validation.md)

## Troubleshooting

- **Symptom:** Connection refused or host key errors. **Fix:** Ensure SSH service is running on Proxmox, add host keys via `ssh-keyscan`, and avoid disabling host key checking in production.
- **Symptom:** `Permission denied (publickey)`. **Fix:** Load key into ssh-agent or set `proxmox_ssh_key_path`; verify key permissions (`chmod 600`) and format (`BEGIN OPENSSH PRIVATE KEY`).
- **Symptom:** CI key not found. **Fix:** Store key in pipeline secrets, write to disk with correct permissions, set `TF_VAR_proxmox_ssh_key_path`, and add known hosts.

---

Last updated: 2025-11-29 14:19 GMT
