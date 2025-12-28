# InfraFoundry Plugin System Documentation

This directory contains comprehensive design documentation for InfraFoundry's plugin system.

## Overview

InfraFoundry uses a **generic, extensible plugin architecture** that supports multiple types of plugins:

- **Providers**: Infrastructure management (Proxmox, AWS, LXD, etc.)
- **Secret Backends**: Secret management (Vault, AWS Secrets Manager, env vars, etc.)
- **Reporters**: Custom output formats (PDF, HTML, Grafana, etc.) *(future)*
- **Analyzers**: Analysis tools (cost, security, compliance, etc.) *(future)*
- **Exporters**: Documentation generators (Confluence, Wiki, etc.) *(future)*
- **Hooks**: Lifecycle event handlers (notifications, approvals, etc.) *(future)*

## Documentation Files

### Core Design

**[PLUGIN_SYSTEM_DESIGN.md](./PLUGIN_SYSTEM_DESIGN.md)** - Main plugin system design
- Generic plugin infrastructure (type-agnostic)
- Plugin type discovery via entry points
- Plugin type system and registry
- Discovery and lifecycle mechanisms
- Built-in plugin types (provider, secret backend)
- Future plugin types (reporters, analyzers, etc.)

### Built-in Plugin Types

**[SECRET_BACKEND_DESIGN.md](./SECRET_BACKEND_DESIGN.md)** - Secret backend plugin type design
- Secret backend protocol
- Built-in backends (env, file)
- Secret resolution system
- Provider integration
- Security considerations
- Third-party backends (Vault, AWS, Azure)

**[PROXMOX_PROVIDER_DESIGN.md](./PROXMOX_PROVIDER_DESIGN.md)** - Proxmox provider plugin design
- Package structure
- Provider implementation details
- CLI integration
- Resource handlers (VM, Container, Snapshot)
- Testing strategy
- Migration plan

### Implementation Guides

**[CLI_DESIGN.md](./CLI_DESIGN.md)** - CLI design and user experience
- Plugin discovery commands (`plugins list`, `plugins search`)
- Error message patterns (standardized, actionable)
- Help system and command structure
- Plugin information commands
- Marketplace integration

**[PROJECT_STRUCTURE.md](./PROJECT_STRUCTURE.md)** - Project structure and UV workspace
- Monorepo structure
- UV workspace configuration
- Package organization (core, providers, meta-package)
- Development workflow
- Build and release process

## Architecture Principles

### Two-Layer Architecture

```
┌─────────────────────────────────────────┐
│ Generic Plugin Infrastructure           │
│ - Plugin type discovery                 │
│ - Discovery (any entry point group)     │
│ - Generic registry                      │
│ - Lifecycle management                  │
└─────────────────────────────────────────┘
                 ↕
┌─────────────────────────────────────────┐
│ Plugin Type Implementations             │
│ - Provider type                         │
│ - Secret backend type                   │
│ - Reporter type (future)                │
│ - Analyzer type (future)                │
└─────────────────────────────────────────┘
                 ↕
┌─────────────────────────────────────────┐
│ Actual Plugins (packages)               │
│ - infrafoundry-proxmox                  │
│ - infrafoundry-lxd                      │
│ - infrafoundry-vault-secrets            │
│ - infrafoundry-cost-analyzer (future)   │
└─────────────────────────────────────────┘
```

### Key Concepts

1. **Generic Infrastructure**: Core plugin system knows nothing about specific plugin types
2. **Plugin Types**: Define protocols and validation for their category
3. **Plugins**: Implement plugin type protocols as separate packages
4. **Entry Points**: Python standard mechanism for plugin discovery
5. **Lazy Loading**: Plugins discovered at startup, instantiated when needed

## Getting Started

### For Plugin Users

Install only the plugins you need:

```bash
# Minimal install
uv pip install infrafoundry-core
uv pip install infrafoundry-proxmox

# Or bundled install
uv pip install infrafoundry  # Includes all official plugins
```

### For Plugin Developers

To create a new provider plugin:

1. Read [PLUGIN_SYSTEM_DESIGN.md](./PLUGIN_SYSTEM_DESIGN.md) - Understand the architecture
2. Read [PROXMOX_PROVIDER_DESIGN.md](./PROXMOX_PROVIDER_DESIGN.md) - See a reference implementation
3. Implement the `BaseProvider` protocol
4. Create a `register()` function
5. Declare entry point in `pyproject.toml`
6. Test discovery and registration

### For Plugin Type Developers

To create a new plugin type (e.g., reporter, analyzer):

1. Read the "Plugin Type System" section in [PLUGIN_SYSTEM_DESIGN.md](./PLUGIN_SYSTEM_DESIGN.md)
2. Implement the `PluginType` protocol
3. Define your plugin protocol (e.g., `BaseReporter`)
4. Register your plugin type at startup
5. Document the interface for plugin authors

## Implementation Status

- [ ] Phase 1: Generic plugin infrastructure
  - [ ] Plugin type discovery via entry points
  - [ ] Generic registry and lifecycle
- [ ] Phase 2: Built-in plugin types
  - [ ] Provider plugin type
  - [ ] Secret backend plugin type (env, file backends)
- [ ] Phase 3: Extract Proxmox provider
  - [ ] Integrate with secret resolution
- [ ] Phase 4: Validation & documentation
- [ ] Phase 5: Extract remaining providers (LXD, Terraform)
- [ ] Future: Reporter, analyzer, exporter plugin types

## Questions or Feedback

For questions about the plugin system design, please refer to:
- The "Open Questions" section in PLUGIN_SYSTEM_DESIGN.md
- The "Success Criteria" sections in each document
- Create an issue in the repository

---

**Last Updated:** 2025-12-28
**Version:** 2.0 (Generic plugin system)
