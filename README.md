# InfraFoundry

**A pluggable infrastructure automation framework built on Terraform, Ansible, and Python.**

InfraFoundry enables reproducible, multi-provider infrastructure deployment with a focus on simplicity, security, and CI/CD integration.

## Features

- 🔌 **Pluggable Providers**: Proxmox, OPNsense, Kubernetes (extensible to ESXi, Docker, cloud providers)
- 🔐 **Secure Secrets**: SOPS with age encryption for secrets shared between Terraform and Ansible
- 📝 **Declarative Config**: YAML configuration files separated by resource type
- � **Separate Config Repos**: Keep infrastructure configs in separate repository from framework
- �🚀 **CI/CD Ready**: GitHub Actions and GitLab CI examples with auto-approve
- 🐍 **Modern Python**: Built with Python 3.11+, uv package manager, type hints
- 🔄 **Reproducible**: Complete environment definition in version control
- 🎯 **Developer Friendly**: direnv integration, rich CLI with colored output

## Architecture

InfraFoundry separates framework code from infrastructure configurations:

**Framework Repository** (this repo):
- Core framework and provider plugins
- Template rendering engine
- CLI and orchestration logic
- Provider implementations (Proxmox, OPNsense, Kubernetes)

**Configuration Repository** (separate, user-maintained):
- Environment definitions (`envs/dev/`, `envs/prod/`)
- Resource configurations (VMs, firewall rules, deployments)
- Encrypted secrets (credentials, tokens)
- Infrastructure-specific settings

This separation allows:
- Independent version control of framework vs infrastructure
- Private configs with public/shared framework
- Multiple config repos using the same framework
- Different access controls for developers vs operators

See [Separate Configuration Repository Guide](docs/separate-config-repo.md) for details.

## Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) - Fast Python package installer
- [Terraform](https://www.terraform.io/) >= 1.6
- [Ansible](https://www.ansible.com/) >= 2.15
- [SOPS](https://github.com/getsops/sops) - For secret management
- [age](https://github.com/FiloSottile/age) - For encryption keys
- [direnv](https://direnv.net/) - Optional but recommended

### Installation

**Option 1: Separate Configuration Repository (Recommended)**

```bash
# Install the framework
git clone https://github.com/yourusername/infrafoundry.git
cd infrafoundry
uv pip install -e .

# Create your configuration repository from example
cp -r example-config ../my-infrastructure-config
cd ../my-infrastructure-config

# Set up environment to point to your config repo
cp .envrc.local.example .envrc.local
# Edit .envrc.local and add:
# export INFRAFOUNDRY_CONFIG_REPO="$(pwd)"
direnv allow

# Initialize secrets
infra secrets init

# Verify setup
infra envs
```

**Option 2: Embedded Configuration (Legacy)**

```bash
# Clone the repository
git clone https://github.com/yourusername/infrafoundry.git
cd infrafoundry

# Install dependencies with uv
uv pip install -e .

# Set up direnv (recommended)
cp .envrc.local.example .envrc.local
# Edit .envrc.local with your credentials
direnv allow

# Generate encryption key for secrets
infra secrets init

# Verify installation
infra --version
```

> **Note:** The separate configuration repository pattern is recommended for better separation of concerns, easier team collaboration, and independent versioning. See [docs/separate-config-repo.md](docs/separate-config-repo.md) for details.

### Basic Usage

**With separate configuration repository:**

```bash
# Set INFRAFOUNDRY_CONFIG_REPO in .envrc.local or export it
export INFRAFOUNDRY_CONFIG_REPO="/path/to/my-infrastructure-config"

# Or use --config-dir flag
infra --config-dir /path/to/my-infrastructure-config envs

# List available environments
infra envs

# Plan infrastructure changes
infra plan --env dev

# Apply infrastructure
infra apply --env dev

# Check status
infra status --env dev

# Destroy infrastructure
infra destroy --env dev
```

**With embedded configuration (legacy):**

```bash
# Commands work the same, configs are in ./envs/
infra envs
infra plan --env dev
infra apply --env dev
```

## CLI Commands

### Resource Management

```bash
# List all resources in an environment
infra list --env dev

# Filter by provider
infra list --env dev --provider proxmox

# Filter by resource type
infra list --env dev --type vms

# Combine filters
infra list --env dev --provider proxmox --type vms
```

### Infrastructure Operations

```bash
# Plan changes (all resources)
infra plan --env dev

# Plan changes (specific resources)
infra plan --env dev --resource web-01
infra plan --env dev --resource web-01 --resource web-02

# Plan with dry-run (no file generation)
infra plan --env dev --dry-run

# Apply changes (all resources)
infra apply --env dev

# Apply specific resources only
infra apply --env dev --resource web-01

# Destroy infrastructure
infra destroy --env dev

# Destroy specific resources
infra destroy --env dev --resource web-01
```

### Environment Management

```bash
# List available environments
infra envs

# Show status of deployed infrastructure
infra status --env dev
```

### Secret Management

```bash
# Initialize age encryption key
infra secrets init

# Encrypt a secrets file
infra secrets encrypt secrets/proxmox.yaml

# Decrypt and view a secrets file
infra secrets decrypt secrets/proxmox.yaml
```

### Multiple Configuration Files

InfraFoundry supports organizing resources across multiple YAML files:

```bash
# All these files will be loaded as "vms" type:
envs/dev/proxmox/vms.yaml            # Main VMs
envs/dev/proxmox/vms-webservers.yaml # Web server VMs
envs/dev/proxmox/vms-databases.yaml  # Database VMs

# Plan includes all VMs from all files
infra plan --env dev

# Target specific VM from any file
infra plan --env dev --resource db-01
```

## Project Structure

**Framework Repository** (this repo):

```
infrafoundry/
├── src/infrafoundry/          # Core framework
│   ├── core/                  # Base classes and managers
│   │   ├── provider.py        # Provider base class
│   │   ├── config.py          # Configuration management
│   │   ├── secrets.py         # SOPS secret management
│   │   └── orchestrator.py    # Deployment orchestration
│   ├── providers/             # Provider plugins
│   │   ├── proxmox/           # Proxmox VE provider
│   │   ├── opnsense/          # OPNsense provider
│   │   └── kubernetes/        # Kubernetes provider
│   └── cli.py                 # Command-line interface
├── example-config/            # Example configuration repository
│   ├── envs/                  # Example environments
│   ├── secrets/               # Example secrets setup
│   ├── .envrc.local.example   # Environment template
│   ├── .gitignore             # Config repo gitignore
│   └── README.md              # Config repo documentation
├── ci/                        # CI/CD integration helpers
├── docs/                      # Documentation
│   ├── separate-config-repo.md # Config repo guide
│   ├── plugin-development.md  # Provider development guide
│   └── direnv.md              # direnv setup guide
├── .envrc                     # direnv framework defaults
├── Makefile                   # Development tasks
└── pyproject.toml             # Python project configuration
```

**Configuration Repository** (separate, user-maintained):

```
my-infrastructure-config/
├── envs/                      # Environment configurations
│   ├── dev/                   # Development environment
│   │   ├── environment.yaml   # Environment definition
│   │   ├── proxmox/           # Proxmox resources
│   │   ├── opnsense/          # OPNsense resources
│   │   └── kubernetes/        # Kubernetes resources
│   ├── staging/               # Staging environment
│   └── prod/                  # Production environment
├── secrets/                   # Encrypted secrets (git-ignored keys)
│   ├── age.key                # Encryption key (DO NOT COMMIT)
│   ├── .sops.yaml             # SOPS configuration (committed)
│   └── *.yaml                 # Encrypted credential files (committed)
├── generated/                 # Generated files (git-ignored)
│   ├── terraform/             # Generated .tf files
│   └── ansible/               # Generated playbooks
├── .envrc.local               # User-specific settings (git-ignored)
├── .gitignore                 # Ignore secrets and generated files
└── README.md                  # Infrastructure documentation
```

## Configuration

### Environment Structure

Each environment (dev, staging, prod) has:

```yaml
# envs/dev/environment.yaml
name: dev
description: Development environment
variables:
  environment: development
  region: us-east
```

**Note:** Providers are auto-discovered from resource files. No need to declare them in `environment.yaml`.

### Provider Resources

InfraFoundry supports two configuration patterns:

#### 1. Provider-Centric (Traditional)

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

#### 2. Resource-Centric (Recommended for Multi-Provider Services)

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
infra secrets encrypt secrets/proxmox.yaml

# Decrypt and view
infra secrets decrypt secrets/proxmox.yaml

# Secrets are automatically decrypted during deployment
```

### Example Secrets File

```yaml
# secrets/proxmox.yaml (before encryption)
proxmox_api_url: https://proxmox.example.com:8006/api2/json
proxmox_api_token_id: user@pam!token
proxmox_api_token_secret: your-secret-token
```

## CI/CD Integration

### GitHub Actions

```yaml
# .github/workflows/infra-deploy.yml
name: Deploy Infrastructure
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: ./ci/setup-ci.sh dev
      - run: infra apply --env dev --auto-approve
```

### GitLab CI

See `.gitlab-ci.yml.example` for complete configuration.

### Required CI Secrets

- `SOPS_AGE_KEY` - Base64-encoded age key
- `PROXMOX_API_*` - Proxmox credentials
- `OPNSENSE_API_*` - OPNsense credentials
- `KUBECONFIG` - Kubernetes config (optional)

## Development

### Adding a New Provider

1. Create provider module:

```python
# src/infrafoundry/providers/yourprovider/__init__.py
from infrafoundry.core.provider import ProviderBase

class YourProvider(ProviderBase):
    def get_resource_types(self) -> list[str]:
        return ["resources", "configs"]

    def generate_terraform(self, resources):
        # Generate .tf files from templates
        pass

    def generate_ansible(self, resources):
        # Generate playbooks from templates
        pass
```

2. Create Jinja2 templates in `providers/yourprovider/templates/`
3. Register in `cli.py`
4. Add example configs in `envs/dev/yourprovider/`

### Running Tests

```bash
make test
```

### Code Formatting

```bash
make format
make lint
```

## Common Tasks

```bash
# Development workflow
make install          # Install dependencies
make dev              # Install with dev dependencies
make plan ENV=dev     # Plan infrastructure
make apply ENV=dev    # Apply infrastructure
make destroy ENV=dev  # Destroy infrastructure

# Code quality
make test             # Run tests
make lint             # Run linters
make format           # Format code
make check            # Run all checks

# Tools
python tools/opnsense-parser.py config.xml  # Parse OPNsense config
```

## Tools

### OPNsense Configuration Parser

Extract and convert OPNsense XML configurations to structured YAML files:

```bash
# Parse OPNsense backup
python tools/opnsense-parser.py ~/Downloads/config-OPNsense.xml

# Parse with custom output directory
python tools/opnsense-parser.py config.xml -o my-configs

# Parse directly to config repo
python tools/opnsense-parser.py config.xml \
  -o $INFRAFOUNDRY_CONFIG_REPO/envs/prod/opnsense
```

**Exports:**
- System settings (hostname, DNS, timezone)
- Network interfaces and VLANs
- Gateways and routing
- Firewall rules and aliases
- NAT configurations
- DHCP servers with static mappings
- OpenVPN clients

**Documentation:** See [docs/tools/opnsense-parser.md](docs/tools/opnsense-parser.md) for full details.

## Troubleshooting

### SOPS Errors

```bash
# Verify age key exists
ls -la $SOPS_AGE_KEY_FILE

# Test decryption
sops --decrypt secrets/proxmox.yaml
```

### Terraform State

```bash
# View state
cd generated/terraform/proxmox
terraform show

# Import existing resources
terraform import proxmox_vm_qemu.my_vm <vmid>
```

### Provider Issues

```bash
# Check provider is registered
infra envs

# Verify templates exist
ls src/infrafoundry/providers/*/templates/
```

## Architecture

- **Core Framework**: Provider base class, config/secret managers, orchestrator
- **Providers**: Pluggable modules implementing provider-specific logic
- **Templates**: Jinja2 templates for generating Terraform and Ansible
- **CLI**: Click-based command-line interface with rich output
- **Orchestrator**: Coordinates provider execution and dependency management

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure `make check` passes
5. Submit a pull request

## License

[Add your license here]

## Support

- Issues: https://github.com/yourusername/infrafoundry/issues
- Discussions: https://github.com/yourusername/infrafoundry/discussions
- Documentation: https://infrafoundry.readthedocs.io
