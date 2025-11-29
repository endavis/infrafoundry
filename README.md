# InfraFoundry

**A pluggable infrastructure code generator and orchestration framework for Terraform and Ansible.**

[![Tests](https://github.com/endavis/infrafoundry/actions/workflows/tests.yml/badge.svg)](https://github.com/endavis/infrafoundry/actions/workflows/tests.yml)
[![Coverage](https://img.shields.io/badge/coverage-70%25-brightgreen)](https://github.com/endavis/infrafoundry)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

InfraFoundry generates Terraform and Ansible configurations from YAML definitions, then optionally orchestrates their execution. It enables reproducible, multi-provider infrastructure deployment with a focus on simplicity, security, and CI/CD integration.

**🎯 YAML-Only Configuration:** You write only YAML - InfraFoundry automatically generates all Terraform `.tf` files and Ansible playbooks. No HCL knowledge required!

## Features

### Core Infrastructure Management
- 🔌 **Pluggable Providers**: Proxmox, OPNsense, Kubernetes (extensible to ESXi, Docker, cloud providers)
- 🔐 **Secure Secrets**: SOPS with age encryption for secrets shared between Terraform and Ansible
- 📝 **Declarative Config**: YAML configuration files separated by resource type
- 🏗️ **Separate Config Repos**: Keep infrastructure configs in separate repository from framework
- 🚀 **CI/CD Ready**: GitHub Actions and GitLab CI examples with auto-approve
- 🐍 **Modern Python**: Built with Python 3.12+, uv package manager, type hints
- 🔄 **Reproducible**: Complete environment definition in version control
- 🎯 **Developer Friendly**: direnv integration, rich CLI with colored output

### Advanced Operations (Fully Implemented)
- 📊 **State Tracking**: Full deployment history and resource lifecycle tracking (SQLite/PostgreSQL)
- 🔍 **Event System**: Hook into any point in the deployment lifecycle
- 🌐 **Dependency Resolution**: Smart dependency graphs with circular detection and impact analysis
- 🔎 **Drift Detection**: Detect infrastructure changes made outside InfraFoundry
- 📊 **Impact Analysis**: Analyze downstream effects before making changes
- ✅ **Pre-flight Validation**: Comprehensive validation before deployment (connectivity, resources, credentials)
- 🛡️ **Policy Enforcement**: Pluggable policy engine for resource limits, naming conventions, and compliance
- ⚡ **Parallel Execution**: Deploy independent providers simultaneously for faster operations
- 🔄 **Automated Rollback**: Revert to previous known-good deployments
- 🔧 **Migration Tools**: ISC to Kea DHCP migration, configuration imports

## Quick Start

### Prerequisites

- Python 3.12+
- [doit](https://pydoit.org/) - Task runner (installed automatically via uv)
- [uv](https://github.com/astral-sh/uv) - Fast Python package installer (installed automatically)
- [Terraform](https://www.terraform.io/) >= 1.6 (installed automatically)
- [Ansible](https://www.ansible.com/) >= 2.15 (installed automatically)
- [SOPS](https://github.com/getsops/sops) - For secret management (installed automatically)
- [age](https://github.com/FiloSottile/age) - For encryption keys (installed automatically)
- [direnv](https://direnv.net/) - Optional but recommended (installed automatically)

### Installation

**Option 1: Automated Setup with Dependencies (Recommended)**

```bash
# Clone the repository
git clone https://github.com/yourusername/infrafoundry.git
cd infrafoundry

# Install all dependencies (just, uv, terraform, ansible, sops, age, direnv)
./scripts/setup-dependencies.sh

# Then run the interactive configuration wizard
./scripts/setup-config.sh
```

**Option 2: Manual Installation**

See [Setup Guide](docs/SETUP_GUIDE.md) for manual installation steps.

## Documentation

### Getting Started
- **[CLI Reference](docs/CLI_REFERENCE.md)** - Complete command reference with examples
- **[Setup Guide](docs/SETUP_GUIDE.md)** - Initial configuration and setup walkthrough
- **[Architecture Overview](docs/architecture/overview.md)** - System architecture, design, and how it works

### Core Guides
- **[Configuration Guide](docs/configuration.md)** - Environment and resource configuration
- **[Separate Configuration Repository](docs/separate-config-repo.md)** - Best practices for organizing infrastructure configs
- **[State Management Strategies](docs/state-management.md)** - Understanding and managing Terraform state, InfraFoundry state, and generated files
- **[Per-Environment Credentials](docs/per-environment-credentials.md)** - Managing different credentials for dev, staging, and production
- **[Policy Configuration](docs/policy-configuration.md)** - Guide to defining and enforcing infrastructure policies
- **[ISC to Kea DHCP Migration](docs/isc-to-kea-migration.md)** - Complete guide for migrating from legacy ISC DHCP to Kea DHCP
- **[direnv Setup](docs/direnv.md)** - Environment variable management

### Development
- **[Plugin Development](docs/development/plugin-development.md)** - Creating custom provider plugins
- **[Event System Guide](docs/development/event-system.md)** - Understanding the internal event bus and notifications
- **[Manager Patterns](docs/development/manager-patterns.md)** - Standard patterns for managers and 3-layer architecture
- **[Architectural Patterns](docs/architecture/architectural-patterns.md)** - Core patterns and best practices

### Tool Documentation
- **[OPNsense Parser](docs/tools/opnsense-parser.md)** - Converting OPNsense XML configs to YAML

## Contributing

We welcome contributions! Please follow these guidelines:

1. **Fork the repository** and create a feature branch
2. **Write tests** for new functionality (maintain 70% coverage)
3. **Run quality checks** before committing:
   ```bash
   doit format        # Format code with ruff
   doit lint          # Run ruff linting
   doit coverage      # Run tests with coverage (must pass 69% threshold)
   ```
4. **Submit a pull request** with clear description

See [docs/development/TESTING_STATUS.md](docs/development/TESTING_STATUS.md) for testing status and [docs/development/ci-cd-testing.md](docs/development/ci-cd-testing.md) for testing guide.

## License

[Add your license here]

## Support

- Issues: https://github.com/yourusername/infrafoundry/issues
- Discussions: https://github.com/yourusername/infrafoundry/discussions
- Documentation: https://infrafoundry.readthedocs.io