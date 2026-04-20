# CLI Design and User Experience

**Version:** 1.0
**Date:** 2025-12-28
**Status:** Design Phase (partially superseded — see below)
**Related:** [Plugin System Design](./PLUGIN_SYSTEM_DESIGN.md),
[ADR-0005: Provider CLI extensibility](../decisions/0005-provider-cli-extensibility.md)

!!! note "Superseded by ADR-0005"
    This document sketches `foundry <provider>` (e.g. `foundry proxmox vm
    list`) as the provider CLI surface. The implementation in
    [ADR-0005](../decisions/0005-provider-cli-extensibility.md) chose
    `foundry provider <name>` instead — so the real commands are
    `foundry provider proxmox dump`, `foundry provider proxmox export`,
    and so on. Treat `Entry: foundry <name>` and similar references below
    as historical; they keep the generic top-level (`config`, `infra`,
    `state`, ...) stable regardless of how many providers ship.

## Table of Contents

1. [Overview](#overview)
2. [Plugin Discovery Commands](#plugin-discovery-commands)
3. [Error Message Patterns](#error-message-patterns)
4. [Help System](#help-system)
5. [Plugin Information Commands](#plugin-information-commands)
6. [Marketplace Integration](#marketplace-integration)

---

## Overview

### Goals

1. **Discoverability**: Users can easily find available plugins
2. **Clear Errors**: When things go wrong, users know exactly what to do
3. **Consistency**: All plugins follow the same CLI patterns
4. **Helpful Guidance**: Error messages suggest solutions

### Design Principles

- **Explicit over implicit**: Clear about what's happening
- **Actionable errors**: Every error suggests how to fix it
- **Progressive disclosure**: Basic info by default, detailed with flags
- **No surprises**: Predictable command structure

---

## Plugin Discovery Commands

### Core Plugin Commands

```bash
# List all plugin types
foundry plugins types

# List all installed plugins
foundry plugins list

# List plugins by type
foundry plugins list --type provider
foundry plugins list --type secret_backend

# Search for plugins (queries PyPI)
foundry plugins search <query>
foundry plugins search proxmox
foundry plugins search vault --type secret_backend

# Show plugin details
foundry <plugin-name> info
foundry proxmox info
```

### `foundry plugins types`

**Purpose**: Show all registered plugin types

**Output:**
```
Plugin Types:
  provider         Infrastructure providers (2 installed)
  secret_backend   Secret management backends (2 installed)

To see plugins of a specific type:
  foundry plugins list --type <type>
```

**Implementation:**
```python
@plugins_group.command()
def types():
    """List all plugin types."""
    type_registry = get_type_registry()
    plugin_registry = get_registry()

    click.echo("Plugin Types:")
    for type_name in type_registry.list_types():
        plugin_type = type_registry.get_type(type_name)
        installed_count = len(plugin_registry.list_by_type(type_name))

        click.echo(f"  {type_name:<16} {plugin_type.description} ({installed_count} installed)")

    click.echo()
    click.echo("To see plugins of a specific type:")
    click.echo("  foundry plugins list --type <type>")
```

---

### `foundry plugins list`

**Purpose**: Show all installed plugins

**Basic Output:**
```
Installed Plugins:

Providers (2):
  proxmox (v0.1.0) - Proxmox Virtual Environment
  lxd (v0.1.0)     - LXD containers

Secret Backends (2):
  env (v0.1.0)  - Environment variables (default)
  file (v0.1.0) - JSON file storage
```

**With `--type` filter:**
```bash
$ foundry plugins list --type provider

Providers (2):
  proxmox (v0.1.0) - Proxmox Virtual Environment
    Resources: vm, container, snapshot
    Entry: foundry proxmox

  lxd (v0.1.0) - LXD containers
    Resources: container, image
    Entry: foundry lxd
```

**With `--verbose` flag:**
```bash
$ foundry plugins list --verbose

Providers (2):
  proxmox (v0.1.0)
    Description: Proxmox Virtual Environment
    Author: InfraFoundry Team
    Package: infrafoundry-proxmox
    Entry Point: infrafoundry_proxmox:register
    Resource Types: vm, container, snapshot
    Commands: foundry proxmox

  lxd (v0.1.0)
    Description: LXD containers
    Author: InfraFoundry Team
    Package: infrafoundry-lxd
    Entry Point: infrafoundry_lxd:register
    Resource Types: container, image
    Commands: foundry lxd

Secret Backends (2):
  env (v0.1.0)
    Description: Environment variables (default)
    Read-Only: Yes
    Package: built-in

  file (v0.1.0)
    Description: JSON file storage
    Read-Only: No
    Package: built-in
```

**Implementation:**
```python
@plugins_group.command()
@click.option("--type", "plugin_type", help="Filter by plugin type")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed information")
def list(plugin_type: Optional[str], verbose: bool):
    """List installed plugins."""
    registry = get_registry()

    if plugin_type:
        # List specific type
        plugins = registry.list_by_type(plugin_type)
        _display_plugins_by_type(plugin_type, plugins, verbose)
    else:
        # List all types
        all_plugins = registry.list_all()

        click.echo("Installed Plugins:")
        click.echo()

        for ptype, plugins in all_plugins.items():
            _display_plugins_by_type(ptype, plugins, verbose)
            click.echo()
```

---

### `foundry plugins search`

**Purpose**: Search for plugins on PyPI

**Output:**
```bash
$ foundry plugins search proxmox

Found on PyPI:

Providers:
  infrafoundry-proxmox (v0.1.0)
    Proxmox Virtual Environment provider
    Install: uv pip install infrafoundry-proxmox

  infrafoundry-proxmox-backup (v0.2.0)
    Proxmox Backup Server integration
    Install: uv pip install infrafoundry-proxmox-backup

No results in other plugin types.
```

**With `--type` filter:**
```bash
$ foundry plugins search vault --type secret_backend

Found on PyPI:

Secret Backends:
  infrafoundry-vault-secrets (v0.1.0)
    HashiCorp Vault integration
    Author: InfraFoundry Community
    Install: uv pip install infrafoundry-vault-secrets
```

**Not found:**
```bash
$ foundry plugins search nonexistent

No plugins found matching 'nonexistent'.

Try:
  - Check spelling
  - Browse all plugins: foundry plugins search ""
  - Visit: https://pypi.org/search/?q=infrafoundry-
```

**Implementation:**
```python
@plugins_group.command()
@click.argument("query")
@click.option("--type", "plugin_type", help="Filter by plugin type")
def search(query: str, plugin_type: Optional[str]):
    """Search for plugins on PyPI."""
    import requests

    # Search PyPI for packages starting with infrafoundry-
    url = "https://pypi.org/pypi?%3Aaction=search"
    params = {"term": f"infrafoundry-{query}"}

    # Parse results and group by plugin type
    # (Implementation details...)
```

---

### `foundry <plugin> info`

**Purpose**: Show detailed information about a specific plugin

**Example:**
```bash
$ foundry proxmox info

Proxmox Provider (v0.1.0)

Description:
  Proxmox Virtual Environment provider for managing VMs, containers, and storage.

Package Information:
  Package: infrafoundry-proxmox
  Author: InfraFoundry Team
  License: MIT
  Homepage: https://github.com/infrafoundry/infrafoundry-proxmox

Capabilities:
  Resource Types: vm, container, snapshot
  CLI Commands: vm, container, snapshot, storages

Requirements:
  Core Version: >=0.1.0,<1.0.0
  Python: >=3.11

Configuration:
  Required: host, user, token_name, token_value
  Optional: verify_ssl, timeout, node

Usage Examples:
  foundry proxmox vm list
  foundry proxmox vm create --vmid 100 --node pve1
  foundry proxmox container status --vmid 200

Documentation:
  https://docs.infrafoundry.dev/providers/proxmox
```

**Implementation:**
```python
# Each plugin type's CLI registration can add an 'info' command
def register_cli(group: click.Group):
    @group.command()
    def info():
        """Show detailed information about this provider."""
        metadata = get_registry().get("provider", group.name)
        _display_plugin_info(metadata)
```

---

## Error Message Patterns

### Standard Error Format

All error messages follow this pattern:

```
Error: <What went wrong>

<Context about the situation>

<Actionable suggestion>
```

---

### Plugin Not Found

**Scenario**: User tries to use a plugin that isn't installed

```bash
$ foundry proxmox vm list
Error: Command 'proxmox' not found.

This looks like a provider command, but 'proxmox' is not installed.

Installed providers:
  lxd, terraform

Search for this plugin:
  foundry plugins search proxmox

Or install directly:
  uv pip install infrafoundry-proxmox
```

**Implementation Strategy:**
1. Click raises `click.UsageError` for unknown commands
2. We intercept it and check if it looks like a plugin command
3. Search installed plugins of likely type
4. Provide helpful suggestions

**Code:**
```python
def handle_unknown_command(ctx, cmd_name):
    """Handle unknown command errors."""
    registry = get_registry()

    # Check if this looks like a provider command
    # (heuristic: unknown command at top level)
    if ctx.parent is None or ctx.parent.info_name == "foundry":
        # Likely a provider
        installed = registry.list_by_type("provider")
        installed_names = [p.name for p in installed]

        click.echo(f"Error: Command '{cmd_name}' not found.", err=True)
        click.echo()
        click.echo(f"This looks like a provider command, but '{cmd_name}' is not installed.")
        click.echo()
        click.echo("Installed providers:")
        click.echo(f"  {', '.join(installed_names)}")
        click.echo()
        click.echo("Search for this plugin:")
        click.echo(f"  foundry plugins search {cmd_name}")
        click.echo()
        click.echo("Or install directly:")
        click.echo(f"  uv pip install infrafoundry-{cmd_name}")

        ctx.exit(1)
```

---

### Secret Not Found

**Scenario**: Secret reference can't be resolved

```bash
$ foundry proxmox vm list
Error: Secret 'proxmox/token' not found in env backend.

The configuration references: secret://proxmox/token

With the 'env' backend, this maps to environment variable:
  PROXMOX_TOKEN

Set this variable:
  export PROXMOX_TOKEN=your-token-here

Or use a different secret backend:
  foundry config set secrets.backend file
```

**Implementation:**
```python
class SecretNotFoundError(Exception):
    """Secret not found in backend."""

    def __init__(self, key: str, backend_name: str):
        self.key = key
        self.backend_name = backend_name

        # Get backend-specific help
        backend = get_secret_backend()
        help_text = backend.get_not_found_help(key)

        message = f"Secret '{key}' not found in {backend_name} backend.\n\n"
        message += help_text

        super().__init__(message)
```

**Backend-Specific Help:**
```python
class EnvSecretBackend:
    def get_not_found_help(self, key: str) -> str:
        env_var = self._key_to_env_var(key)
        return f"""The configuration references: secret://{key}

With the 'env' backend, this maps to environment variable:
  {env_var}

Set this variable:
  export {env_var}=your-secret-value

Or use a different secret backend:
  foundry config set secrets.backend file"""


class FileSecretBackend:
    def get_not_found_help(self, key: str) -> str:
        return f"""The configuration references: secret://{key}

With the 'file' backend, this should be in: {self.path}

Add this secret:
  foundry secrets set {key} your-secret-value

Or view all secrets:
  foundry secrets list"""
```

---

### Version Incompatibility

**Scenario**: Plugin requires different core version

**At Discovery Time:**
```bash
$ foundry plugins list

Warning: Some plugins could not be loaded:

  proxmox (v2.0.0) - Version incompatibility
    Requires: infrafoundry-core >=2.0.0
    Installed: infrafoundry-core 1.5.0

    Upgrade core:
      uv pip install --upgrade infrafoundry-core>=2.0.0

    Or downgrade plugin:
      uv pip install infrafoundry-proxmox<2.0.0

Installed Plugins:
  lxd (v0.1.0)
  terraform (v0.1.0)
```

**At Runtime:**
```bash
$ foundry proxmox vm list
Error: Provider 'proxmox' is not available.

The 'proxmox' plugin is installed but incompatible:
  Plugin version: 2.0.0
  Requires core: >=2.0.0
  Installed core: 1.5.0

Upgrade core:
  uv pip install --upgrade infrafoundry-core>=2.0.0

Or downgrade plugin:
  uv pip install infrafoundry-proxmox<2.0.0
```

**Implementation:**
```python
def check_version_compatibility(metadata: PluginMetadata) -> VersionCheckResult:
    """Check if plugin is compatible with current core version."""
    required = metadata.metadata.get("requires_core_version")
    if not required:
        return VersionCheckResult(compatible=True)

    current = CORE_VERSION

    if not version_satisfies(current, required):
        return VersionCheckResult(
            compatible=False,
            plugin_version=metadata.version,
            required_core=required,
            current_core=current,
            upgrade_command=f"uv pip install --upgrade infrafoundry-core{required}",
            downgrade_command=find_compatible_version(metadata.name, current),
        )

    return VersionCheckResult(compatible=True)
```

---

### Plugin Load Failure

**Scenario**: Plugin installed but fails to load (import error, etc.)

```bash
$ foundry plugins list

Warning: Some plugins could not be loaded:

  custom-provider (v0.1.0) - Load failed
    Error: ImportError: No module named 'required_dependency'

    This plugin may have missing dependencies.
    Try reinstalling:
      uv pip install --force-reinstall infrafoundry-custom-provider

    Or check plugin documentation:
      foundry plugins info custom-provider

Installed Plugins:
  proxmox (v0.1.0)
  lxd (v0.1.0)
```

**Implementation:**
```python
def discover_plugins(self, plugin_type: PluginType) -> Tuple[List[PluginMetadata], List[PluginLoadError]]:
    """
    Discover plugins, returning both successful and failed loads.

    Returns:
        Tuple of (loaded_plugins, failed_plugins)
    """
    loaded = []
    failed = []

    eps = entry_points(group=plugin_type.entry_point_group)

    for ep in eps:
        try:
            metadata = plugin_type.load_plugin(ep)
            validation = plugin_type.validate_plugin(metadata)

            if validation.valid:
                loaded.append(metadata)
            else:
                failed.append(PluginLoadError(
                    name=ep.name,
                    error_type="validation_failed",
                    error_message="; ".join(validation.errors),
                ))
        except Exception as e:
            failed.append(PluginLoadError(
                name=ep.name,
                error_type=type(e).__name__,
                error_message=str(e),
                traceback=traceback.format_exc(),
            ))

    return loaded, failed
```

---

## Help System

### Command Help

Every command has consistent help output:

```bash
$ foundry proxmox vm create --help

Usage: foundry proxmox vm create [OPTIONS]

  Create a new Proxmox VM.

Options:
  --vmid INTEGER        VM ID (required)
  --node TEXT           Proxmox node (required)
  --name TEXT           VM name
  --cores INTEGER       CPU cores (default: 1)
  --memory INTEGER      Memory in MB (default: 1024)
  --help                Show this message and exit.

Examples:
  foundry proxmox vm create --vmid 100 --node pve1 --name web-server
  foundry proxmox vm create --vmid 101 --node pve1 --cores 4 --memory 8192

Configuration:
  Provider config: ~/.config/infrafoundry/infrafoundry.yaml

See also:
  foundry proxmox vm list       List all VMs
  foundry proxmox vm status     Get VM status
  foundry proxmox info          Provider information
```

---

### Top-Level Help

```bash
$ foundry --help

Usage: foundry [OPTIONS] COMMAND [ARGS]...

  InfraFoundry - Infrastructure as Code orchestration

Options:
  --version             Show version and exit
  --config PATH         Config file path
  --log-level LEVEL     Logging level (debug, info, warn, error)
  --help               Show this message and exit.

Core Commands:
  config               Configuration management
  state                State file operations
  plugins              Plugin management

Provider Commands:
  proxmox              Proxmox Virtual Environment
  lxd                  LXD containers
  terraform            Terraform resources

Secret Commands:
  secrets              Secret management

Get help for a command:
  foundry <command> --help

Getting Started:
  foundry plugins list          List installed plugins
  foundry config show           Show current configuration
  foundry proxmox info          Learn about a provider
```

---

## Plugin Information Commands

### Provider Info

Each provider should implement an `info` command:

```bash
$ foundry proxmox info

Proxmox Provider (v0.1.0)

Description:
  Manage Proxmox VE virtual machines, containers, and storage.

Configuration:
  Required:
    host          Proxmox API endpoint (https://host:8006)
    user          Username (e.g., root@pam)
    token_name    API token name
    token_value   API token secret (use secret://path)

  Optional:
    verify_ssl    Verify SSL certificates (default: true)
    timeout       API timeout in seconds (default: 30)
    node          Default node name

Example Configuration:
  providers:
    proxmox:
      host: "https://proxmox.example.com:8006"
      user: "root@pam"
      token_name: "api-token"
      token_value: "secret://proxmox/token"
      verify_ssl: false

Available Commands:
  vm               VM management (list, create, status, control)
  container        Container management
  snapshot         Snapshot operations
  storages         List available storage

Resource Types:
  vm              Virtual machines (QEMU)
  container       LXC containers
  snapshot        VM/container snapshots

Documentation:
  https://docs.infrafoundry.dev/providers/proxmox

Support:
  Issues: https://github.com/infrafoundry/infrafoundry-proxmox/issues
  Discussions: https://github.com/infrafoundry/infrafoundry-proxmox/discussions
```

---

## Marketplace Integration

### Phase 1: PyPI Search (MVP)

Use PyPI's JSON API to search for plugins:

```python
def search_pypi(query: str, plugin_type: Optional[str] = None) -> List[PyPIPackage]:
    """Search PyPI for InfraFoundry plugins."""

    # Search for packages starting with infrafoundry-
    url = f"https://pypi.org/pypi/{query}/json"

    # Or use search API
    search_url = "https://pypi.org/search/"
    params = {"q": f"infrafoundry-{query}"}

    # Parse results
    # Filter by plugin type if specified
    # Return structured data
```

### Phase 2: Curated Registry (Future)

Maintain a curated list of verified plugins:

```json
{
  "plugins": [
    {
      "name": "proxmox",
      "package": "infrafoundry-proxmox",
      "type": "provider",
      "description": "Proxmox Virtual Environment provider",
      "author": "InfraFoundry Team",
      "verified": true,
      "documentation": "https://docs.infrafoundry.dev/providers/proxmox",
      "repository": "https://github.com/infrafoundry/infrafoundry-proxmox",
      "tags": ["virtualization", "proxmox", "vm", "container"]
    }
  ]
}
```

Host this on GitHub and fetch at runtime:

```bash
$ foundry plugins browse

InfraFoundry Plugin Marketplace

Providers (3):
  [✓] proxmox - Proxmox Virtual Environment
      ⭐ Official • 1.2k downloads • Updated 2 days ago

  [ ] aws - Amazon Web Services
      ⭐ Official • 850 downloads • Updated 1 week ago

  [ ] kubernetes - Kubernetes clusters
      Community • 420 downloads • Updated 3 weeks ago

Secret Backends (2):
  [✓] vault - HashiCorp Vault
      Community • 320 downloads • Updated 1 month ago

  [ ] aws - AWS Secrets Manager
      Community • 180 downloads • Updated 2 months ago

Legend: [✓] Installed  [ ] Not installed  ⭐ Official

Commands:
  ↑/↓    Navigate
  Space  Toggle selection
  Enter  Install/uninstall selected
  i      Show plugin info
  q      Quit
```

---

## Implementation Checklist

### Core CLI Commands
- [ ] `foundry plugins types`
- [ ] `foundry plugins list`
- [ ] `foundry plugins list --type <type>`
- [ ] `foundry plugins search <query>`
- [ ] `foundry <plugin> info` (template for plugin types)

### Error Handling
- [ ] Unknown command handler (suggests installed plugins)
- [ ] `SecretNotFoundError` with backend-specific help
- [ ] Version incompatibility warnings at discovery
- [ ] Plugin load failure reporting
- [ ] Consistent error format across all commands

### Help System
- [ ] Rich help text for all commands
- [ ] Examples in help output
- [ ] Cross-references between related commands
- [ ] Top-level help with grouped commands

### Plugin Type Integration
- [ ] Provider plugin type adds `info` command to each provider
- [ ] Secret backend plugin type adds secret management commands
- [ ] Plugin types contribute to `plugins list` output
- [ ] Plugin types provide error message formatting

---

## User Experience Scenarios

### Scenario 1: New User Setup

```bash
# User installs InfraFoundry
$ uv pip install infrafoundry

# Explores what's available
$ foundry --help
$ foundry plugins list
$ foundry proxmox info

# Configures provider
$ foundry config create
$ export PROXMOX_TOKEN=xxx

# Uses provider
$ foundry proxmox vm list
```

### Scenario 2: Installing New Plugin

```bash
# User hears about Vault secrets
$ foundry plugins search vault

# Installs it
$ uv pip install infrafoundry-vault-secrets

# Verifies installation
$ foundry plugins list --type secret_backend

# Configures it
$ foundry config set secrets.backend vault
$ foundry secrets --help
```

### Scenario 3: Troubleshooting

```bash
# Command fails
$ foundry proxmox vm list
Error: Secret 'proxmox/token' not found in env backend.
...

# User follows suggestion
$ export PROXMOX_TOKEN=xxx

# Works!
$ foundry proxmox vm list
```

### Scenario 4: Version Conflict

```bash
# User upgrades plugin
$ uv pip install --upgrade infrafoundry-proxmox

# Plugin incompatible
$ foundry plugins list
Warning: Some plugins could not be loaded:
  proxmox (v2.0.0) - Version incompatibility
  ...

# User upgrades core
$ uv pip install --upgrade infrafoundry-core

# Fixed!
$ foundry plugins list
```

---

## Success Criteria

- [ ] Users can discover plugins without leaving CLI
- [ ] Every error message suggests a solution
- [ ] Help text is comprehensive and includes examples
- [ ] Plugin loading failures are explicit and actionable
- [ ] Version conflicts are caught early with clear upgrade paths
- [ ] CLI is consistent across all plugin types
- [ ] New users can get started without reading docs
