# Project Structure and UV Workspace

**Version:** 1.0
**Date:** 2025-12-28
**Status:** Design Phase
**Related:** [Plugin System Design](./PLUGIN_SYSTEM_DESIGN.md)

## Table of Contents

1. [Overview](#overview)
2. [Monorepo Structure](#monorepo-structure)
3. [UV Workspace Configuration](#uv-workspace-configuration)
4. [Package Organization](#package-organization)
5. [Development Workflow](#development-workflow)
6. [Build and Release](#build-and-release)

---

## Overview

### Monorepo Approach

InfraFoundry uses a **monorepo** with multiple packages:

**Benefits:**
- Coordinated changes across core and plugins
- Shared development tools and configuration
- Easier testing of plugin integration
- Single source of truth for versions

**Structure:**
- Each package is independently installable
- Packages can depend on each other
- UV workspace manages dependencies
- Can still publish separately to PyPI

### UV Workspace

UV's workspace feature manages multiple packages in one repository:
- Shared lock file for development
- Local package references (no need to publish)
- Coordinated version bumps
- Unified testing and CI

---

## Monorepo Structure

### Directory Layout

```
infrafoundry/                          # Repository root
├── .github/
│   ├── workflows/
│   │   ├── ci.yml                     # Main CI pipeline
│   │   ├── test-plugins.yml           # Plugin-specific tests
│   │   └── release.yml                # Release automation
│   └── PULL_REQUEST_TEMPLATE.md
│
├── docs/                              # Documentation
│   ├── plugin_system/                 # Plugin system designs
│   │   ├── PLUGIN_SYSTEM_DESIGN.md
│   │   ├── SECRET_BACKEND_DESIGN.md
│   │   ├── PROXMOX_PROVIDER_DESIGN.md
│   │   ├── CLI_DESIGN.md
│   │   ├── PROJECT_STRUCTURE.md
│   │   └── README.md
│   ├── user_guide/                    # User documentation
│   │   ├── getting_started.md
│   │   ├── configuration.md
│   │   └── providers/
│   └── developer_guide/               # Developer docs
│       ├── writing_plugins.md
│       └── contributing.md
│
├── packages/                          # All packages
│   │
│   ├── infrafoundry-core/            # Core package
│   │   ├── src/
│   │   │   └── infrafoundry/
│   │   │       ├── __init__.py
│   │   │       ├── core/             # Core functionality
│   │   │       │   ├── __init__.py
│   │   │       │   ├── plugin_system/
│   │   │       │   │   ├── __init__.py
│   │   │       │   │   ├── plugin_type.py
│   │   │       │   │   ├── plugin_type_registry.py
│   │   │       │   │   ├── discovery.py
│   │   │       │   │   ├── registry.py
│   │   │       │   │   └── exceptions.py
│   │   │       │   ├── config/
│   │   │       │   ├── state/
│   │   │       │   └── orchestrator/
│   │   │       │
│   │   │       ├── providers/        # Provider plugin type
│   │   │       │   ├── __init__.py
│   │   │       │   ├── plugin_type.py
│   │   │       │   ├── protocol.py
│   │   │       │   └── registry.py
│   │   │       │
│   │   │       ├── secrets/          # Secret backend plugin type
│   │   │       │   ├── __init__.py
│   │   │       │   ├── plugin_type.py
│   │   │       │   ├── protocol.py
│   │   │       │   ├── env_backend.py
│   │   │       │   ├── file_backend.py
│   │   │       │   └── exceptions.py
│   │   │       │
│   │   │       └── cli/              # Core CLI
│   │   │           ├── __init__.py
│   │   │           ├── main.py
│   │   │           └── commands/
│   │   │               ├── config.py
│   │   │               ├── state.py
│   │   │               ├── plugins.py
│   │   │               └── analyze.py
│   │   │
│   │   ├── tests/
│   │   │   ├── unit/
│   │   │   │   ├── test_plugin_system/
│   │   │   │   ├── test_config/
│   │   │   │   └── test_state/
│   │   │   └── integration/
│   │   │       ├── test_plugin_discovery.py
│   │   │       └── test_cli.py
│   │   │
│   │   ├── pyproject.toml
│   │   ├── README.md
│   │   └── LICENSE
│   │
│   ├── infrafoundry-proxmox/        # Proxmox provider
│   │   ├── src/
│   │   │   └── infrafoundry_proxmox/
│   │   │       ├── __init__.py
│   │   │       ├── provider.py
│   │   │       ├── cli.py
│   │   │       ├── config.py
│   │   │       ├── exceptions.py
│   │   │       ├── api/
│   │   │       │   ├── __init__.py
│   │   │       │   ├── client.py
│   │   │       │   ├── vm.py
│   │   │       │   ├── container.py
│   │   │       │   └── snapshot.py
│   │   │       ├── resources/
│   │   │       │   ├── __init__.py
│   │   │       │   ├── base.py
│   │   │       │   ├── vm.py
│   │   │       │   ├── container.py
│   │   │       │   └── snapshot.py
│   │   │       └── utils/
│   │   │
│   │   ├── tests/
│   │   │   ├── unit/
│   │   │   └── integration/
│   │   │
│   │   ├── pyproject.toml
│   │   ├── README.md
│   │   └── LICENSE
│   │
│   ├── infrafoundry-lxd/           # LXD provider
│   │   └── ... (similar structure)
│   │
│   ├── infrafoundry-terraform/     # Terraform provider
│   │   └── ... (similar structure)
│   │
│   └── infrafoundry/               # Meta-package (convenience)
│       ├── pyproject.toml          # Depends on all official packages
│       ├── README.md
│       └── LICENSE
│
├── scripts/                         # Development scripts
│   ├── setup_dev.sh                # Setup development environment
│   ├── test_all.sh                 # Run all tests
│   ├── bump_version.py             # Version management
│   └── release.py                  # Release automation
│
├── pyproject.toml                  # Workspace root config
├── uv.lock                         # Unified lock file
├── README.md                       # Repository README
├── LICENSE
└── .gitignore
```

---

## UV Workspace Configuration

### Root `pyproject.toml`

**File**: `pyproject.toml` (repository root)

```toml
[project]
# Root is not a package itself, just workspace coordinator
name = "infrafoundry-workspace"
version = "0.1.0"
description = "InfraFoundry monorepo workspace"
requires-python = ">=3.11"

[tool.uv]
# Dev dependencies for workspace
dev-dependencies = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
    "pytest-mock>=3.11",
    "mypy>=1.5",
    "ruff>=0.1.0",
    "black>=23.0",
]

[tool.uv.workspace]
# All packages in the workspace
members = [
    "packages/infrafoundry-core",
    "packages/infrafoundry-proxmox",
    "packages/infrafoundry-lxd",
    "packages/infrafoundry-terraform",
    "packages/infrafoundry",
]

[tool.pytest.ini_options]
testpaths = ["packages/*/tests"]
python_files = "test_*.py"
python_functions = "test_*"
addopts = "--verbose --cov=infrafoundry --cov-report=term-missing"

[tool.mypy]
python_version = "3.11"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
plugins = ["pydantic.mypy"]

[[tool.mypy.overrides]]
module = "tests.*"
disallow_untyped_defs = false

[tool.ruff]
line-length = 88
target-version = "py311"
select = ["E", "F", "I", "N", "W"]
ignore = ["E501"]  # Line too long (handled by black)

[tool.ruff.per-file-ignores]
"__init__.py" = ["F401"]  # Unused imports in __init__

[tool.black]
line-length = 88
target-version = ['py311']
```

---

### Core Package `pyproject.toml`

**File**: `packages/infrafoundry-core/pyproject.toml`

```toml
[project]
name = "infrafoundry-core"
version = "0.1.0"
description = "InfraFoundry core - Plugin system and orchestration"
readme = "README.md"
requires-python = ">=3.11"
license = {text = "MIT"}
authors = [
    {name = "InfraFoundry Team", email = "team@infrafoundry.dev"}
]
keywords = ["infrastructure", "iac", "orchestration", "plugins"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
]

# Core dependencies
dependencies = [
    "click>=8.0",
    "pyyaml>=6.0",
    "pydantic>=2.0",
    "rich>=13.0",  # For nice CLI output
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
    "pytest-mock>=3.11",
    "mypy>=1.5",
    "ruff>=0.1.0",
]

# Entry points for plugin types
[project.entry-points."infrafoundry.plugin_types"]
provider = "infrafoundry.providers.plugin_type:ProviderPluginType"
secret_backend = "infrafoundry.secrets.plugin_type:SecretBackendPluginType"

# Entry points for built-in secret backends
[project.entry-points."infrafoundry.secrets"]
env = "infrafoundry.secrets.env_backend:register"
file = "infrafoundry.secrets.file_backend:register"

# CLI entry point
[project.scripts]
foundry = "infrafoundry.cli.main:cli"

[project.urls]
Homepage = "https://infrafoundry.dev"
Documentation = "https://docs.infrafoundry.dev"
Repository = "https://github.com/infrafoundry/infrafoundry"
Issues = "https://github.com/infrafoundry/infrafoundry/issues"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/infrafoundry"]
```

---

### Provider Package `pyproject.toml`

**File**: `packages/infrafoundry-proxmox/pyproject.toml`

```toml
[project]
name = "infrafoundry-proxmox"
version = "0.1.0"
description = "Proxmox provider for InfraFoundry"
readme = "README.md"
requires-python = ">=3.11"
license = {text = "MIT"}
authors = [
    {name = "InfraFoundry Team", email = "team@infrafoundry.dev"}
]
keywords = ["infrafoundry", "proxmox", "provider", "plugin"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
]

# Dependencies
dependencies = [
    "infrafoundry-core>=0.1.0,<1.0.0",  # Core plugin system
    "proxmoxer>=2.0.0",                  # Proxmox API client
    "requests>=2.31.0",                  # HTTP client
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
    "pytest-mock>=3.11",
]

# Entry point to register as provider
[project.entry-points."infrafoundry.providers"]
proxmox = "infrafoundry_proxmox:register"

[project.urls]
Homepage = "https://infrafoundry.dev"
Documentation = "https://docs.infrafoundry.dev/providers/proxmox"
Repository = "https://github.com/infrafoundry/infrafoundry"
Issues = "https://github.com/infrafoundry/infrafoundry/issues"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/infrafoundry_proxmox"]
```

---

### Meta-package `pyproject.toml`

**File**: `packages/infrafoundry/pyproject.toml`

```toml
[project]
name = "infrafoundry"
version = "0.1.0"
description = "InfraFoundry - Complete installation with all official plugins"
readme = "README.md"
requires-python = ">=3.11"
license = {text = "MIT"}
authors = [
    {name = "InfraFoundry Team", email = "team@infrafoundry.dev"}
]
keywords = ["infrastructure", "iac", "orchestration"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
]

# Bundle all official packages
dependencies = [
    "infrafoundry-core==0.1.0",
    "infrafoundry-proxmox==0.1.0",
    "infrafoundry-lxd==0.1.0",
    "infrafoundry-terraform==0.1.0",
]

[project.urls]
Homepage = "https://infrafoundry.dev"
Documentation = "https://docs.infrafoundry.dev"
Repository = "https://github.com/infrafoundry/infrafoundry"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

# This is a meta-package with no actual code
[tool.hatch.build.targets.wheel]
packages = []
```

**Purpose:**
- Convenience package that installs everything
- `uv pip install infrafoundry` gets core + all official providers
- Users can also install minimal: `uv pip install infrafoundry-core infrafoundry-proxmox`

---

## Package Organization

### Core Package

**Namespace**: `infrafoundry`

**Responsibilities:**
- Generic plugin system
- Built-in plugin types (provider, secret backend)
- Core CLI commands
- Configuration management
- State management
- Orchestration logic

**Key Modules:**
```
infrafoundry.core.plugin_system     # Generic plugin infrastructure
infrafoundry.providers              # Provider plugin type
infrafoundry.secrets                # Secret backend plugin type
infrafoundry.cli                    # Core CLI
infrafoundry.config                 # Configuration
infrafoundry.state                  # State management
```

---

### Provider Packages

**Namespace**: `infrafoundry_<provider>` (underscore, not dash)

**Example**: `infrafoundry_proxmox`, `infrafoundry_lxd`

**Responsibilities:**
- Implement provider protocol
- Resource type handlers
- Provider-specific CLI commands
- API client wrapper

**Key Modules:**
```
infrafoundry_proxmox                # Package root
├── __init__.py                     # Exports register()
├── provider.py                     # ProxmoxProvider class
├── cli.py                          # CLI registration
├── config.py                       # Configuration model
├── api/                            # API client
├── resources/                      # Resource handlers
└── utils/                          # Utilities
```

---

### Third-Party Packages

**Naming Convention**: `infrafoundry-<plugin-name>`

**Examples:**
- `infrafoundry-vault-secrets`
- `infrafoundry-aws-provider`
- `infrafoundry-kubernetes-provider`
- `infrafoundry-cost-analyzer`

**Guidelines:**
- Follow same structure as official plugins
- Use `infrafoundry_<name>` as Python package name
- Declare appropriate entry point
- Document configuration and usage

---

## Development Workflow

### Initial Setup

```bash
# Clone repository
git clone https://github.com/infrafoundry/infrafoundry.git
cd infrafoundry

# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install workspace in editable mode
uv sync

# This installs all packages in development mode
# Changes to any package are immediately available
```

### Running Tests

```bash
# Test everything
uv run pytest

# Test specific package
uv run pytest packages/infrafoundry-core/tests

# Test with coverage
uv run pytest --cov=infrafoundry --cov-report=html

# Test specific file
uv run pytest packages/infrafoundry-core/tests/unit/test_plugin_system/test_discovery.py
```

### Linting and Formatting

```bash
# Lint everything
uv run ruff check .

# Fix auto-fixable issues
uv run ruff check --fix .

# Format code
uv run black .

# Type checking
uv run mypy packages/infrafoundry-core/src
```

### Local Development

```bash
# Make changes to any package
vim packages/infrafoundry-core/src/infrafoundry/core/plugin_system/discovery.py

# Test immediately (packages installed in editable mode)
uv run pytest packages/infrafoundry-core/tests/unit/test_plugin_system/test_discovery.py

# Try in CLI
uv run foundry plugins list
```

### Adding a New Package

```bash
# Create package structure
mkdir -p packages/infrafoundry-newprovider/src/infrafoundry_newprovider
mkdir -p packages/infrafoundry-newprovider/tests

# Add to workspace
# Edit root pyproject.toml:
[tool.uv.workspace]
members = [
    # ...existing members
    "packages/infrafoundry-newprovider",
]

# Install in editable mode
uv sync

# Package is now available in development
```

---

## Build and Release

### Building Packages

```bash
# Build specific package
cd packages/infrafoundry-core
uv build

# Build all packages
./scripts/build_all.sh
```

### Version Management

```bash
# Bump version across all packages
./scripts/bump_version.py --version 0.2.0

# This updates:
# - All pyproject.toml files
# - Meta-package dependencies
# - __version__ in __init__.py files
```

### Release Process

```bash
# 1. Run full test suite
uv run pytest

# 2. Bump versions
./scripts/bump_version.py --version 0.2.0

# 3. Commit version bump
git add .
git commit -m "chore: bump version to 0.2.0"
git tag v0.2.0

# 4. Build all packages
./scripts/build_all.sh

# 5. Publish to PyPI (in order)
uv publish packages/infrafoundry-core/dist/*
uv publish packages/infrafoundry-proxmox/dist/*
uv publish packages/infrafoundry-lxd/dist/*
uv publish packages/infrafoundry-terraform/dist/*
uv publish packages/infrafoundry/dist/*

# 6. Push to GitHub
git push origin main --tags
```

### CI/CD Pipeline

**File**: `.github/workflows/ci.yml`

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12"]

    steps:
      - uses: actions/checkout@v3

      - name: Install uv
        uses: astral-sh/setup-uv@v1

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v4
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install workspace
        run: uv sync

      - name: Lint
        run: |
          uv run ruff check .
          uv run mypy packages/infrafoundry-core/src

      - name: Test
        run: uv run pytest --cov=infrafoundry --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml

  test-plugins:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        package: [infrafoundry-proxmox, infrafoundry-lxd, infrafoundry-terraform]

    steps:
      - uses: actions/checkout@v3
      - uses: astral-sh/setup-uv@v1

      - name: Test ${{ matrix.package }}
        run: |
          uv sync
          uv run pytest packages/${{ matrix.package }}/tests
```

---

## Success Criteria

- [ ] UV workspace configured with all packages
- [ ] Packages installable in editable mode
- [ ] Tests run across all packages
- [ ] Linting and formatting configured
- [ ] Local dependencies work (provider depends on core)
- [ ] CI pipeline tests all packages
- [ ] Release process documented
- [ ] Version bumping automated
- [ ] Meta-package bundles all official plugins

---

## Next Steps

1. Create initial monorepo structure
2. Set up UV workspace
3. Implement core package with plugin system
4. Extract first provider (Proxmox)
5. Test workspace integration
6. Set up CI/CD
7. Document development workflow
