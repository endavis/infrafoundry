# Settings File Structure

## Overview

InfraFoundry uses a single, SOPS-encrypted `settings.yaml` file per environment containing all configuration and secrets. **You write only YAML** - InfraFoundry automatically generates Terraform `.tf` and `.tfvars` files from your settings. No HCL knowledge required!

## File Location

```
envs/
├── dev/
│   ├── settings.yaml        # All config + secrets (SOPS encrypted)
│   ├── proxmox/             # Resource definitions (not encrypted)
│   │   └── vm.yaml
│   └── resources/           # Multi-provider resources (not encrypted)
│       └── app.yaml
├── staging/
│   └── settings.yaml
└── prod/
    └── settings.yaml
```

## Structure

```yaml
# envs/prod/settings.yaml (can be encrypted with SOPS)

# Environment metadata
name: prod
description: Production environment
variables:
  datacenter: dc1
  domain: example.com
  managed_by: infrafoundry

# Global SSH defaults (applies to all providers unless overridden)
ssh:
  user: automation
  key_path: /home/automation/.ssh/id_ed25519
  port: 22

# Provider-specific SSH overrides (optional)
provider_ssh:
  proxmox:
    user: root
    key_path: /secure/keys/proxmox_ed25519
    port: 2222
  opnsense:
    user: root
    key_path: /secure/keys/opnsense_ed25519

# Provider-specific settings (credentials, endpoints, defaults)
provider_settings:
  proxmox:
    # API credentials
    api_url: https://pve01.example.com:8006
    api_token: pve-token-id=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
    
    # Provider defaults
    node: pve01
    storage: local-zfs
    
  opnsense:
    # API credentials
    api_url: https://fw.example.com
    api_key: xxxxxxxxxxxxxxxxxxxx
    api_secret: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

## Schema

### Top-Level Fields

```yaml
name: string                # Required: Environment name
description: string         # Optional: Human-readable description
variables: dict            # Optional: Environment variables for templates
ssh: SSHConfig             # Optional: Global SSH defaults
provider_ssh: dict         # Optional: Per-provider SSH overrides
provider_settings: dict    # Optional: Provider-specific settings
```

### SSH Configuration

```yaml
ssh:
  user: string             # Optional: Default SSH user
  key_path: string         # Optional: Path to SSH private key
  port: int                # Optional: SSH port (default: 22)
```

### Provider SSH Overrides

```yaml
provider_ssh:
  <provider_name>:
    user: string           # Optional: Override SSH user for this provider
    key_path: string       # Optional: Override SSH key for this provider
    port: int              # Optional: Override SSH port for this provider
```

### Provider Settings

Each provider can have custom settings for credentials, endpoints, and defaults:

```yaml
provider_settings:
  <provider_name>:
    # Provider-specific fields (varies by provider)
```

## Provider-Specific Fields

### Proxmox

```yaml
provider_settings:
  proxmox:
    api_url: string                    # Required: Proxmox API URL
    api_token: string                  # Required: API token (format: id=secret)
    node: string                       # Optional: Default node
    storage: string                    # Optional: Default storage
```

### OPNsense

```yaml
provider_settings:
  opnsense:
    api_url: string                    # Required: OPNsense API URL
    api_key: string                    # Required: API key
    api_secret: string                 # Required: API secret
```

### Kubernetes

```yaml
provider_settings:
  kubernetes:
    kubeconfig_path: string            # Required: Path to kubeconfig
    context: string                    # Optional: Kube context
    namespace: string                  # Optional: Default namespace
```

## Encryption

The entire `settings.yaml` file should be encrypted with SOPS using age encryption:

```bash
# Create age key (one-time setup)
age-keygen -o secrets/age.key

# Get public key for .sops.yaml
age-keygen -y secrets/age.key

# Create .sops.yaml configuration
cat > .sops.yaml << EOF
creation_rules:
  - path_regex: envs/.*/settings\.yaml$
    age: <PUBLIC_KEY>
EOF

# Encrypt settings
sops --encrypt --age <PUBLIC_KEY> envs/prod/settings.yaml.plain > envs/prod/settings.yaml

# Decrypt for editing
sops envs/prod/settings.yaml

# Decrypt for InfraFoundry (automatic)
export SOPS_AGE_KEY_FILE=secrets/age.key
infra plan --env prod
```

## Migration from Old Structure

### From environment.yaml to settings.yaml

Old structure:
```yaml
# environment.yaml
name: prod
description: Production environment
variables:
  datacenter: dc1
```

New structure - same fields at top level:
```yaml
# settings.yaml
name: prod
description: Production environment
variables:
  datacenter: dc1
provider_settings:
  proxmox:
    # ... provider config
```

### From secrets/ directory to settings.yaml

Old structure:
```
envs/prod/
├── environment.yaml
└── ../../secrets/
    ├── proxmox.yaml (encrypted)
    └── opnsense.yaml (encrypted)
```

New structure:
```
envs/prod/
└── settings.yaml (encrypted, contains everything)
```

Merge credentials from `secrets/*.yaml` into `provider_settings`:

```yaml
# Old: secrets/proxmox.yaml
api_url: https://pve01.example.com:8006
api_token: token-value

# New: settings.yaml
provider_settings:
  proxmox:
    api_url: https://pve01.example.com:8006
    api_token: token-value
```

## Benefits

1. **Single source of truth**: One file per environment
2. **Everything encrypted**: All credentials in one SOPS-encrypted file
3. **Provider isolation**: Each provider's config clearly separated
4. **Flexible SSH**: Global defaults with per-provider overrides
5. **Better CI/CD**: One SOPS key, one file to manage

## Complete Example

See `/endavis-infra/envs/test/settings.yaml` for a comprehensive example with all supported fields.
