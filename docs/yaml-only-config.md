# YAML-Only Configuration

## Overview

InfraFoundry now uses **pure YAML configuration** for all settings. No need to write HCL (Terraform) configuration files - everything is defined in YAML and automatically converted as needed.

## What Changed

**Before:** Users had to write both YAML and HCL
- Resources: YAML files (`envs/{env}/{provider}/*.yaml`)
- SSH config: HCL files (`terraform.tfvars`)

**After:** Everything is YAML
- Resources: YAML files (`envs/{env}/{provider}/*.yaml` or `envs/{env}/resources/*.yaml`)
- Configuration: YAML in `settings.yaml` → automatically converted to `terraform.tfvars`
- Credentials: YAML in `settings.yaml` (encrypted with SOPS) → passed to Terraform

## Configuration File

All environment configuration, including SSH settings and provider credentials, goes in `settings.yaml`:

### Global Config (Simple)

When all providers use the same SSH credentials:

```yaml
# endavis-infra/envs/test/settings.yaml
name: test
description: Test environment

ssh:
  user: endavis
  key_path: /home/endavis/.ssh/id_ed25519
  port: 22  # Optional, defaults to 22

provider_settings:
  proxmox:
    api_url: https://pve01.example.com:8006
    api_token: your-api-token
    node: pve01
    storage: local-lvm
```

### Per-Provider Config (Advanced)

When different providers need different SSH credentials:

```yaml
# endavis-infra/envs/prod/settings.yaml
name: prod
description: Production environment

# Global default (used if provider-specific not defined)
ssh:
  user: automation
  key_path: /home/automation/.ssh/id_ed25519

# Provider-specific SSH overrides
provider_ssh:
  proxmox:
    user: proxmox-admin
    key_path: /secure/keys/proxmox_prod
    port: 2222
  opnsense:
    user: opnsense-admin
    key_path: /secure/keys/opnsense_prod

# Provider credentials and settings
provider_settings:
  proxmox:
    api_url: https://pve01.example.com:8006
    api_token: prod-api-token
    node: pve01
    storage: local-zfs
  opnsense:
    api_url: https://opn.example.com
    api_key: prod-api-key
    api_secret: prod-api-secret
```

### Auto-generated terraform.tfvars

For the per-provider example, Proxmox gets:

```hcl
# Configuration from settings.yaml
proxmox_api_url = "https://pve01.example.com:8006"
proxmox_api_token = "prod-api-token"
proxmox_node = "pve01"
proxmox_storage = "local-zfs"
proxmox_ssh_user = "proxmox-admin"
proxmox_ssh_key_path = "/secure/keys/proxmox_prod"
proxmox_ssh_port = 2222
```

While OPNsense would get its own provider-specific settings.

## Benefits

1. **Consistency**: All configuration uses the same format
2. **Simplicity**: No need to learn HCL syntax
3. **Flexibility**: Per-environment SSH settings without duplicating HCL
4. **Automation**: Framework handles conversion automatically

## Implementation Details

- **Location**: `src/infrafoundry/providers/proxmox/__init__.py`
- **Method**: `_generate_tfvars()` - called during `generate_terraform()`
- **Config Model**: `SSHConfig` in `src/infrafoundry/core/config.py`
- **Generated File**: `generated/{env}/terraform/proxmox/terraform.tfvars`

## Related Documentation

- [SSH Authentication](ssh-authentication.md) - Detailed SSH setup guide
- [Separate Config Repo](separate-config-repo.md) - Repository structure
- [Per-Environment Credentials](per-environment-credentials.md) - Managing secrets
