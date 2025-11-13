# InfraFoundry

**A pluggable infrastructure code generator and orchestration framework for Terraform and Ansible.**

[![Tests](https://github.com/endavis/infrafoundry/actions/workflows/tests.yml/badge.svg)](https://github.com/endavis/infrafoundry/actions/workflows/tests.yml)
[![Coverage](https://img.shields.io/badge/coverage-70%25-brightgreen)](https://github.com/endavis/infrafoundry)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

InfraFoundry generates Terraform and Ansible configurations from YAML definitions, then optionally orchestrates their execution. It enables reproducible, multi-provider infrastructure deployment with a focus on simplicity, security, and CI/CD integration.

**🎯 YAML-Only Configuration:** You write only YAML - InfraFoundry automatically generates all Terraform `.tf` files and Ansible playbooks. No HCL knowledge required!

## What InfraFoundry Does

**Primary: Infrastructure as Code Generation**
- Reads declarative YAML configurations for your infrastructure
- Generates Terraform `.tf` files for resource provisioning
- Generates Ansible playbooks for post-deployment configuration
- Supports multiple providers: Proxmox, OPNsense, Kubernetes

**Secondary: Tool Orchestration**
- Optionally executes `terraform init/plan/apply/destroy`
- Optionally runs `ansible-playbook` for configuration management
- Coordinates multi-provider deployments with dependency resolution
- Does NOT replace Terraform/Ansible - it generates configs and orchestrates their execution

## Features

- 🔌 **Pluggable Providers**: Proxmox, OPNsense, Kubernetes (extensible to ESXi, Docker, cloud providers)
- 🔐 **Secure Secrets**: SOPS with age encryption for secrets shared between Terraform and Ansible
- 📝 **Declarative Config**: YAML configuration files separated by resource type
- 🏗️ **Separate Config Repos**: Keep infrastructure configs in separate repository from framework
- 🚀 **CI/CD Ready**: GitHub Actions and GitLab CI examples with auto-approve
- 🐍 **Modern Python**: Built with Python 3.12+, uv package manager, type hints
- 🔄 **Reproducible**: Complete environment definition in version control
- 🎯 **Developer Friendly**: direnv integration, rich CLI with colored output
- 📊 **State Tracking**: Full deployment history and resource lifecycle tracking
- 🔍 **Event System**: Hook into any point in the deployment lifecycle
- 🌐 **Dependency Resolution**: Smart dependency graphs with circular detection
- 📈 **Foundation for Advanced Features**: Drift detection, impact analysis, automated rollback

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
  ```bash
  # Install uv (recommended method)
  curl -LsSf https://astral.sh/uv/install.sh | sh

  # Or with pip (if uv not available)
  pip install uv
  ```
- [Terraform](https://www.terraform.io/) >= 1.6
- [Ansible](https://www.ansible.com/) >= 2.15
- [SOPS](https://github.com/getsops/sops) - For secret management
- [age](https://github.com/FiloSottile/age) - For encryption keys
- [direnv](https://direnv.net/) - Optional but recommended

### Installation

**Option 1: Interactive Setup (Recommended)**

```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone the repository
git clone https://github.com/yourusername/infrafoundry.git
cd infrafoundry

# Install dependencies with uv
uv pip install -e .

# Run the interactive setup wizard
./scripts/setup-config.sh

# The wizard will:
# - Check for and install uv if needed
# - Guide you through configuration choices
# - Create environment files
# - Set up secrets management
# - Generate .envrc.local for direnv
```

**Option 2: Separate Configuration Repository (Manual)**

```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install the framework
git clone https://github.com/yourusername/infrafoundry.git
cd infrafoundry
uv pip install -e .

# Create your configuration repository from example
cp -r example-config ../my-infrastructure-config
cd ../my-infrastructure-config

# Set up environment to point to your config repo
cp docs/examples/.envrc.local.example .envrc.local
# Edit .envrc.local and add:
# export INFRAFOUNDRY_CONFIG_REPO="$(pwd)"
direnv allow

# Initialize secrets
infra secrets init

# Verify setup
infra envs
```

> **Note:** The interactive setup wizard (`scripts/setup-config.sh`) is the easiest way to get started. It automates configuration creation, secret management setup, and environment variable configuration. For manual setup or CI/CD environments, use Option 2 (separate config repo).

## How It Works

InfraFoundry follows a clear workflow that separates code generation from execution:

### 1. Plan (Generate Only)

```bash
infra plan --env dev
```

**What happens:**
- ✅ Reads YAML configs from `envs/dev/`
- ✅ Validates resources and dependencies
- ✅ Generates Terraform files → `generated/{env}/terraform/{provider}/`
- ✅ Generates Ansible playbooks → `generated/{env}/ansible/{provider}/`
- ❌ Does NOT execute terraform or ansible
- ❌ Does NOT create any infrastructure

**Output:** Generated `.tf` files and playbooks ready for review

### 2. Apply (Generate + Execute)

```bash
infra apply --env dev
```

**What happens:**
- ✅ Generates configs (same as plan)
- ✅ Runs `terraform init` (first time only)
- ✅ Runs `terraform apply` for each provider
- ✅ Runs `ansible-playbook` (if playbooks exist)
- ✅ Tracks deployment in state database

**Result:** Infrastructure is provisioned and configured

### 3. Destroy (Execute Removal)

```bash
infra destroy --env dev
```

**What happens:**
- ✅ Runs `terraform destroy` for each provider
- ✅ Updates state database

### Generated Files Structure

```
generated/
├── dev/                         # Environment: dev
│   ├── terraform/
│   │   ├── proxmox/
│   │   │   ├── main.tf          # Generated from YAML
│   │   │   ├── variables.tf     # Generated from YAML
│   │   │   ├── outputs.tf       # Generated from YAML
│   │   │   └── .terraform/      # Created by terraform init
│   │   ├── opnsense/
│   │   │   └── ...
│   │   └── kubernetes/
│   │       └── ...
│   └── ansible/
│       ├── proxmox/
│       │   ├── playbook.yml     # Generated from YAML
│       │   ├── inventory.yml    # Generated from YAML
│       │   └── roles/           # Your custom roles
│       └── ...
├── staging/                     # Environment: staging
│   ├── terraform/
│   └── ansible/
└── prod/                        # Environment: prod
    ├── terraform/
    └── ansible/
```

**Key Point:** Each environment has its own directory with separate Terraform state!

- ✅ Can work on dev and prod simultaneously
- ✅ Terraform state isolated per environment
- ✅ No risk of overwriting one environment with another
- ✅ Clear separation for team collaboration

**You can review and manually execute the generated files if you prefer:**

```bash
# Generate configs only
infra plan --env dev

# Manually review generated files
cd generated/dev/terraform/proxmox
cat main.tf

# Manually execute (instead of infra apply)
terraform init
terraform plan
terraform apply

# Run Ansible separately
cd ../../ansible/proxmox
ansible-playbook -i inventory.yml playbook.yml
```

**For production:** Configure remote Terraform backend in your generated files to share state with your team.

### Basic Usage

**With separate configuration repository:**

```bash
# Set INFRAFOUNDRY_CONFIG_REPO in .envrc.local or export it
export INFRAFOUNDRY_CONFIG_REPO="/path/to/my-infrastructure-config"

# Or use --config-dir flag
infra --config-dir /path/to/my-infrastructure-config envs

# Initialize state tracking (first-time setup)
infra init

# List available environments
infra envs

# Plan infrastructure changes
infra plan --env dev

# View deployment history
infra history

# Apply infrastructure
infra apply --env dev

# Check status
infra status --env dev

# Destroy infrastructure
infra destroy --env dev
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

### State Management

InfraFoundry tracks deployment history and resource state in a local database:

```bash
# Initialize state database (first-time setup)
infra init

# View deployment history
infra history

# View history for specific environment
infra history --env prod

# Limit number of results
infra history --limit 10
```

State is stored in `~/.infrafoundry/state.db` by default. This enables:
- **Deployment tracking**: See who deployed what and when
- **Resource tracking**: Monitor resource lifecycle and state
- **Audit trails**: Full history of infrastructure changes
- **Future features**: Drift detection, impact analysis, rollback

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
infra secrets encrypt envs/dev/settings.yaml

# Decrypt and view a secrets file
infra secrets decrypt envs/dev/settings.yaml
```

### Reset Operations

Reset (wipe) specific infrastructure components for clean redeployment:

```bash
# Reset Kea DHCPv4 configuration
infra reset --env prod --provider opnsense --component kea/dhcpv4

# Reset Kea DHCPv6 configuration
infra reset --env prod --provider opnsense --component kea/dhcpv6

# Reset both DHCPv4 and DHCPv6
infra reset --env prod --provider opnsense --component kea/dhcp

# Skip confirmation prompt
infra reset --env prod --provider opnsense --component kea/dhcp --auto-approve
```

**Use Cases:**
- Clear existing DHCP config before applying InfraFoundry-managed configuration
- Resolve configuration drift by wiping and reapplying
- Clean slate for testing configuration changes

### Migration Tools

InfraFoundry includes tools to migrate existing infrastructure to code:

```bash
# Migrate existing Kea DHCP configuration from OPNsense
infra migrate --env prod --provider opnsense --component kea/dhcp

# Migrate legacy ISC DHCP to Kea DHCP format (both DHCPv4 and DHCPv6)
infra migrate --env prod --provider opnsense --component isc-to-kea

# Migrate specific interfaces only
infra migrate --env prod --provider opnsense --component isc-to-kea -i lan -i wan

# Preview migration without writing files
infra migrate --env prod --provider opnsense --component isc-to-kea --dry-run

# Custom output location
infra migrate --env prod --provider opnsense --component isc-to-kea \
    -o custom/path/dhcp-config.yaml
```

**ISC to Kea Migration:**
- Converts legacy ISC DHCP (deprecated) to modern Kea DHCP
- Migrates DHCPv4 and DHCPv6 configurations
- Preserves all settings: subnets, pools, DNS, gateway, NTP, static reservations
- Generates InfraFoundry YAML ready for deployment
- See [docs/isc-to-kea-migration.md](docs/isc-to-kea-migration.md) for complete guide

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
│   ├── envs/               # Example environment configurations
│   ├── .gitignore             # Config repo gitignore
│   └── README.md              # Config repo documentation
├── ci/                        # CI/CD integration helpers
├── docs/                      # Documentation
│   ├── examples/              # Example configuration files
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
│   │   ├── settings.yaml      # Environment definition + secrets
│   │   ├── proxmox/           # Proxmox resources
│   │   ├── opnsense/          # OPNsense resources
│   │   └── kubernetes/        # Kubernetes resources
│   ├── staging/               # Staging environment
│   └── prod/                  # Production environment
├── envs/                   # Environment configs with encrypted settings (git-ignored keys)
│   ├── age.key                # Encryption key (DO NOT COMMIT)
│   └── .sops.yaml             # SOPS configuration (committed)
├── generated/                 # Generated files (git-ignored)
│   ├── terraform/             # Generated .tf files
│   └── ansible/               # Generated playbooks
├── .envrc.local               # User-specific settings (git-ignored)
├── .gitignore                 # Ignore secrets and generated files
└── README.md                  # Infrastructure documentation
```

## Configuration

### Environment Structure

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

**SSH Configuration**: Some Proxmox operations (extracting compressed images, disk imports) require SSH access. Configure per-environment SSH settings in `settings.yaml`. Supports both global and per-provider configurations. InfraFoundry will automatically generate the needed Terraform variables. See [docs/ssh-authentication.md](docs/ssh-authentication.md) for details.

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

## CI/CD Integration

InfraFoundry includes comprehensive CI/CD workflows for both testing and deployment.

### Automated Testing (GitHub Actions)

The test workflow (`.github/workflows/tests.yml`) runs on every push and PR:

**Four parallel jobs:**
1. **Main Tests**: Full test suite with coverage (69% threshold)
2. **Python Matrix**: Tests on Python 3.12 and 3.13
3. **Integration Tests**: Tests with Terraform and Ansible installed
4. **Code Quality**: Black, ruff, isort, and mypy checks

**Coverage reporting:**
- Coverage reports uploaded as CI artifacts
- Codecov integration for tracking trends
- PR comments with coverage changes
- Coverage badge auto-updated

**Local testing:**
```bash
make test          # Run all tests
make coverage      # Run with coverage report
make lint          # Run linting
make format        # Format code
```

### Infrastructure Deployment (GitHub Actions)

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

See `docs/examples/.gitlab-ci.yml.example` for complete configuration.

### Required CI Secrets

- `SOPS_AGE_KEY` - Base64-encoded age key
- `PROXMOX_API_*` - Proxmox credentials
- `OPNSENSE_API_*` - OPNsense credentials
- `KUBECONFIG` - Kubernetes config (optional)
- `CODECOV_TOKEN` - Codecov token (optional, for test workflow)

## Development

**Package Management:** This project uses `uv` for all Python package management. Always use `uv pip` commands instead of plain `pip`.

### Adding a New Provider

1. Create provider module:

```python
# src/infrafoundry/providers/yourprovider/__init__.py
from typing import override
from infrafoundry.core.provider import ProviderBase

class YourProvider(ProviderBase):
    @override
    def get_resource_types(self) -> list[str]:
        return ["resources", "configs"]

    @override
    def generate_terraform(self, resources):
        # Generate .tf files from templates
        pass

    @override
    def generate_ansible(self, resources):
        # Generate playbooks from templates
        pass
```

2. Create Jinja2 templates in `providers/yourprovider/templates/`
3. Register in `cli.py`
4. Add example configs in `envs/dev/yourprovider/`

### Installing Dependencies

```bash
# ALWAYS use uv for package management
uv pip install <package>         # Install a package
uv pip install -e .              # Install project in editable mode
uv pip install -e ".[dev]"       # Install with dev dependencies
uv pip list                      # List installed packages
```

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
sops --decrypt envs/dev/settings.yaml
```

### Terraform State

```bash
# View state
cd generated/dev/terraform/proxmox
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

InfraFoundry is built around a clear separation of concerns:

**Code Generation Layer:**
- **Providers**: Pluggable modules (Proxmox, OPNsense, Kubernetes) that implement `ProviderBase`
- **Templates**: Jinja2 templates for generating Terraform `.tf` files and Ansible playbooks
- **Config Manager**: Loads and validates YAML configurations
- **Secret Manager**: Handles SOPS encryption/decryption, exports secrets to Terraform/Ansible

**Orchestration Layer:**
- **Orchestrator**: Coordinates multi-provider deployments, manages dependencies, optionally executes tools
- **CLI**: Click-based command-line interface with rich console output
- **State Manager**: SQLite database tracking deployment history and resource lifecycle
- **Event System**: Hooks for notifications and custom integrations
- **Policy Engine**: Validates resources against organizational policies

**Data Flow:**

```
YAML Configs → ConfigManager → Providers → Jinja2 Templates → Generated Files
                                    ↓
                              Orchestrator (optional)
                                    ↓
                    terraform init/apply  +  ansible-playbook
                                    ↓
                              Infrastructure
```

**Key Design Principles:**
1. **Generation before execution** - Always generate configs first, optionally execute
2. **Provider plugins** - Easy to add new providers (ESXi, AWS, Azure, etc.)
3. **Tool agnostic** - Generated files are standard Terraform/Ansible, work without InfraFoundry
4. **Separate configs** - Framework code separate from infrastructure definitions

## Documentation

### Core Guides
- **[Separate Configuration Repository](docs/separate-config-repo.md)** - Best practices for organizing infrastructure configs
- **[State Management Strategies](docs/state-management.md)** - Understanding and managing Terraform state, InfraFoundry state, and generated files
- **[Per-Environment Credentials](docs/per-environment-credentials.md)** - Managing different credentials for dev, staging, and production
- **[ISC to Kea DHCP Migration](docs/isc-to-kea-migration.md)** - Complete guide for migrating from legacy ISC DHCP to Kea DHCP
- **[Plugin Development](docs/development/plugin-development.md)** - Creating custom provider plugins
- **[direnv Setup](docs/direnv.md)** - Environment variable management

### Tool Documentation
- **[OPNsense Parser](docs/tools/opnsense-parser.md)** - Converting OPNsense XML configs to YAML

### Additional Resources
- [Terraform Backend Configuration](https://www.terraform.io/language/settings/backends)
- [SOPS Documentation](https://github.com/getsops/sops)
- [age Encryption](https://github.com/FiloSottile/age)

## Contributing

We welcome contributions! Please follow these guidelines:

1. **Fork the repository** and create a feature branch
2. **Write tests** for new functionality (maintain 70% coverage)
3. **Run quality checks** before committing:
   ```bash
   make format        # Format code with black
   make lint          # Run ruff linting
   make coverage      # Run tests with coverage (must pass 69% threshold)
   ```
4. **Ensure all checks pass** - CI will verify:
   - All 286+ tests passing
   - Coverage ≥ 69%
   - Code formatting (black)
   - Linting (ruff)
5. **Submit a pull request** with clear description

**Testing Guidelines:**
- Add tests for new features and bug fixes
- Follow existing test patterns in `tests/unit/`
- Use fixtures for common setup
- Mock external dependencies (Terraform, Ansible, APIs)
- Check `htmlcov/index.html` for coverage gaps

See [docs/development/TESTING_STATUS.md](docs/development/TESTING_STATUS.md) for testing status and [docs/development/ci-cd-testing.md](docs/development/ci-cd-testing.md) for testing guide.

## License

[Add your license here]

## Support

- Issues: https://github.com/yourusername/infrafoundry/issues
- Discussions: https://github.com/yourusername/infrafoundry/discussions
- Documentation: https://infrafoundry.readthedocs.io
