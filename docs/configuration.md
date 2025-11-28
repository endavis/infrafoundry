# InfraFoundry Configuration Guide

This guide details how to configure InfraFoundry environments, providers, and resources.

## Environment Structure

Each environment (dev, staging, prod) uses a `settings.yaml` file containing all configuration and credentials:

```yaml
# envs/dev/settings.yaml (encrypt with SOPS)
name: dev
description: Development environment
variables:
  environment: development
  region: us-east

# Optional: Global SSH configuration (all providers)
ssh:
  user: your-username
  key_path: /path/to/ssh/key
  port: 22  # Optional, defaults to 22

# Optional: Per-provider SSH configuration (overrides global)
provider_ssh:
  proxmox:
    user: proxmox-admin
    key_path: /path/to/proxmox/key
    port: 2222

# Optional: Provider-specific settings (credentials, endpoints)
provider_settings:
  proxmox:
    api_url: https://pve01.example.com:8006
    api_token: your-api-token
    node: pve01
    storage: local-lvm
  opnsense:
    api_url: https://opn.example.com
    api_key: your-api-key
    api_secret: your-api-secret
```

**Note:** Providers are auto-discovered from resource files. No need to declare them in `settings.yaml`.

**SSH Configuration**: Some Proxmox operations (extracting compressed images, disk imports) require SSH access. Configure per-environment SSH settings in `settings.yaml`. Supports both global and per-provider configurations. InfraFoundry will automatically generate the needed Terraform variables. See [docs/ssh-authentication.md](../ssh-authentication.md) for details.

## Provider Resources

InfraFoundry supports two configuration patterns:

### 1. Provider-Centric (Traditional)

Resources are organized by provider and type in separate directories:

**Single file per type:**
```
envs/dev/
├── proxmox/
│   ├── vm.yaml
│   ├── template.yaml
│   └── network.yaml
├── opnsense/
│   ├── firewall_rule.yaml
│   ├── vlan.yaml
│   └── alias.yaml
└── kubernetes/
    ├── namespace.yaml
    ├── deployment.yaml
    ├── service.yaml
    └── configmap.yaml
```

**Multiple files per type (recommended for large environments):**
```
envs/prod/
├── proxmox/
│   ├── vm-webservers.yaml       # Web tier VMs
│   ├── vm-databases.yaml        # Database VMs
│   ├── vm-infrastructure.yaml   # Infrastructure VMs
│   ├── template.yaml
│   └── network.yaml
└── kubernetes/
    ├── deployment-frontend.yaml
    ├── deployment-backend.yaml
    └── service.yaml
```

Files are grouped by the prefix before the first dash. For example:
- `vm.yaml`, `vm-web.yaml`, `vm-db.yaml` all map to resource type `vm`
- `deployment.yaml`, `deployment-api.yaml` both map to type `deployment`

**Example provider-centric file:**
```yaml
# envs/dev/proxmox/vm.yaml
vm:
  - name: web-server-01
    target_node: pve01
    clone: ubuntu-22-04-template
    cores: 2
    memory: 4096
```

### 2. Resource-Centric (Recommended for Multi-Provider Services)

Group all infrastructure for a service/application in one file, regardless of provider:

```
envs/prod/
├── resources/
│   ├── web-server.yaml          # VM + firewall + DNS for web server
│   ├── database-cluster.yaml    # Database VMs + networking
│   └── monitoring.yaml          # Monitoring stack across providers
├── proxmox/
│   └── shared-templates.yaml    # Shared resources
└── environment.yaml
```

**Example resource-centric file:**
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
      disk_size: 50
      network:
        bridge: vmbr0
        vlan: 10
      template: ubuntu-22.04-cloudinit

  - provider: opnsense
    type: firewall_rule
    name: allow-web-80
    config:
      action: pass
      interface: LAN
      protocol: tcp
      destination_port: 80
      destination: web-server-01

  - provider: opnsense
    type: firewall_rule
    name: allow-web-443
    config:
      action: pass
      interface: LAN
      protocol: tcp
      destination_port: 443
      destination: web-server-01
```

**Benefits of resource-centric:**
- All infrastructure for a service in one place
- Easier to understand complete service architecture
- Better for GitOps (service changes touch one file)
- Natural cross-provider dependencies
- Organize by business logic, not technical boundaries

**Use provider-centric when:**
- Single provider environment
- Bulk operations on similar resources
- Simple infrastructure

**Use resource-centric when:**
- Multi-provider services
- Complex applications with many components
- Team-based infrastructure (one file per team/service)
- GitOps workflows with PR-based reviews

### Example: Proxmox VM

```yaml
# envs/dev/proxmox/vm.yaml
vm:
  - name: web-server-01
    target_node: pve01
    clone: ubuntu-22-04-template
    cores: 2
    memory: 4096
    disk:
      size: 50G
      storage: local-lvm
    network:
      bridge: vmbr0
      tag: 100
    ipconfig: ip=192.168.100.10/24,gw=192.168.100.1
    tags:
      - webserver
      - nginx
```

## Secret Management

InfraFoundry uses SOPS with age encryption for secrets:

```bash
# Initialize secrets
infra secrets init

# Encrypt a secrets file
infra secrets encrypt envs/dev/settings.yaml

# Decrypt and view
infra secrets decrypt envs/dev/settings.yaml

# Secrets are automatically decrypted during deployment
```

### Example Secrets File

```yaml
# envs/dev/settings.yaml (before encryption)
proxmox_api_url: https://proxmox.example.com:8006/api2/json
proxmox_api_token_id: user@pam!token
proxmox_api_token_secret: your-secret-token
```
