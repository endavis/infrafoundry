# InfraFoundry Plugin System Design

**Version:** 2.0
**Date:** 2025-12-28
**Status:** Design Phase

## Table of Contents

1. [Overview](#overview)
2. [Architecture Philosophy](#architecture-philosophy)
3. [Generic Plugin Infrastructure](#generic-plugin-infrastructure)
4. [Plugin Type System](#plugin-type-system)
5. [Entry Points Mechanism](#entry-points-mechanism)
6. [Plugin Discovery](#plugin-discovery)
7. [Plugin Registry](#plugin-registry)
8. [Plugin Lifecycle](#plugin-lifecycle)
9. [Error Handling](#error-handling)
10. [Provider Plugin Type](#provider-plugin-type)
11. [Future Plugin Types](#future-plugin-types)
12. [Implementation Roadmap](#implementation-roadmap)

---

## Overview

### Vision

InfraFoundry's plugin system enables **extensibility through composition**, not just for infrastructure providers, but for any type of functionality:

- **Providers**: Infrastructure management (Proxmox, AWS, LXD, etc.)
- **Secret Backends**: Secret management (Vault, AWS Secrets Manager, env vars, etc.)
- **Reporters**: Custom output formats (PDF, HTML, Grafana, etc.)
- **Analyzers**: Analysis tools (cost, security, compliance, etc.)
- **Exporters**: Documentation generators (Confluence, Wiki, etc.)
- **Hooks**: Lifecycle event handlers (pre-apply, post-destroy, etc.)
- **State Backends**: State storage systems (S3, PostgreSQL, local, etc.)

### Core Principles

1. **Type Agnostic**: Plugin system knows nothing about specific plugin types
2. **Extensible**: New plugin types can be added without modifying core
3. **Discoverable**: Plugins auto-register via Python entry points
4. **Isolated**: Each plugin is a separate package with its own dependencies
5. **Composable**: Users install only the plugins they need

### Design Goals

- **Generic Infrastructure**: Discovery, registry, and lifecycle work for any plugin type
- **Plugin Type Abstraction**: Each plugin type defines its own interface/protocol
- **Zero Hard-Coding**: Core has no knowledge of specific plugins
- **Third-Party Friendly**: External developers can create plugin types AND plugins

---

## Architecture Philosophy

### Two-Layer Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: Generic Plugin Infrastructure                     │
│ - Plugin type registration                                  │
│ - Generic discovery (any entry point group)                │
│ - Generic registry (stores any plugin type)                │
│ - Lifecycle management                                      │
│ - Error handling                                            │
└─────────────────────────────────────────────────────────────┘
                           ↕
┌─────────────────────────────────────────────────────────────┐
│ Layer 2: Plugin Type Implementations                       │
│ ┌────────────────┐ ┌────────────────┐ ┌────────────────┐  │
│ │ Provider Type  │ │ Reporter Type  │ │ Analyzer Type  │  │
│ │ - Protocol     │ │ - Protocol     │ │ - Protocol     │  │
│ │ - Registry ops │ │ - Registry ops │ │ - Registry ops │  │
│ │ - CLI          │ │ - CLI          │ │ - CLI          │  │
│ └────────────────┘ └────────────────┘ └────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                           ↕
┌─────────────────────────────────────────────────────────────┐
│ Layer 3: Actual Plugins (installed packages)               │
│ ┌────────────┐ ┌────────────┐ ┌─────────────┐             │
│ │ Proxmox    │ │ PDF        │ │ Cost        │             │
│ │ Provider   │ │ Reporter   │ │ Analyzer    │  ...        │
│ └────────────┘ └────────────┘ └─────────────┘             │
└─────────────────────────────────────────────────────────────┘
```

### Separation of Concerns

| Layer | Responsibility | Knows About |
|-------|---------------|-------------|
| **Generic Infrastructure** | Discovery, registry, lifecycle | Plugin types (abstract), entry points |
| **Plugin Type** | Define protocol, validation, type-specific operations | Generic infrastructure, plugin interface |
| **Plugin** | Implement functionality | Plugin type protocol |

### Key Insight

The generic infrastructure treats **plugin types** as plugins themselves:
- Core registers plugin types
- Plugin types define how to discover and manage their plugins
- Allows third parties to add entirely new categories of plugins

---

## Generic Plugin Infrastructure

### Core Components

```
infrafoundry/core/plugin_system/
├── __init__.py              # Public API
├── plugin_type.py           # PluginType abstraction
├── discovery.py             # Generic discovery engine
├── registry.py              # Generic plugin registry
├── lifecycle.py             # Plugin lifecycle management
└── exceptions.py            # Plugin system exceptions
```

### Plugin Type Abstraction

Every plugin type implements the `PluginType` protocol:

**File**: `src/infrafoundry/core/plugin_system/plugin_type.py`

```python
"""Plugin type abstraction."""

from typing import Protocol, Any, Dict, List
from abc import abstractmethod


class PluginMetadata:
    """Generic plugin metadata."""

    name: str                        # Plugin name (e.g., "proxmox", "pdf-reporter")
    version: str                     # Plugin version
    plugin_type: str                 # Type category (e.g., "provider", "reporter")
    description: str                 # Human-readable description
    implementation: Any              # Plugin implementation (class, function, etc.)
    metadata: Dict[str, Any]         # Type-specific metadata


class PluginType(Protocol):
    """
    Protocol that all plugin types must implement.

    This is the contract between the generic plugin infrastructure
    and specific plugin type implementations.
    """

    @property
    @abstractmethod
    def entry_point_group(self) -> str:
        """
        Entry point group to scan.

        Returns:
            Entry point group name (e.g., "infrafoundry.providers")
        """

    @property
    @abstractmethod
    def type_name(self) -> str:
        """
        Human-readable plugin type name.

        Returns:
            Type name (e.g., "provider", "reporter")
        """

    @abstractmethod
    def load_plugin(self, entry_point) -> PluginMetadata:
        """
        Load a plugin from an entry point.

        Args:
            entry_point: Entry point to load

        Returns:
            PluginMetadata for the plugin

        Raises:
            PluginLoadError: If loading fails
        """

    @abstractmethod
    def validate_plugin(self, metadata: PluginMetadata) -> ValidationResult:
        """
        Validate that a plugin implements required interface.

        Args:
            metadata: Plugin metadata to validate

        Returns:
            ValidationResult with any errors
        """

    @abstractmethod
    def register_cli(self, app: Any, plugins: List[PluginMetadata]) -> None:
        """
        Register CLI commands for this plugin type.

        Optional - plugin types can skip CLI registration.

        Args:
            app: Main CLI application
            plugins: All loaded plugins of this type
        """
```

### ValidationResult

```python
from dataclasses import dataclass, field
from typing import List


@dataclass
class ValidationResult:
    """Result of plugin validation."""

    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
```

---

## Plugin Type System

### Plugin Type Registry

The core maintains a registry of plugin types (not plugins themselves):

**File**: `src/infrafoundry/core/plugin_system/plugin_type_registry.py`

```python
"""Registry for plugin types."""

from typing import Dict, Optional
from infrafoundry.core.plugin_system.plugin_type import PluginType


class PluginTypeRegistry:
    """Registry of plugin types."""

    def __init__(self):
        self._types: Dict[str, PluginType] = {}

    def register_type(self, plugin_type: PluginType) -> None:
        """
        Register a plugin type.

        Args:
            plugin_type: Plugin type to register

        Raises:
            PluginTypeAlreadyRegistered: If type already registered
        """
        type_name = plugin_type.type_name

        if type_name in self._types:
            raise PluginTypeAlreadyRegistered(
                f"Plugin type '{type_name}' already registered"
            )

        self._types[type_name] = plugin_type

    def get_type(self, type_name: str) -> PluginType:
        """Get a registered plugin type."""
        if type_name not in self._types:
            raise PluginTypeNotFound(f"Plugin type '{type_name}' not registered")
        return self._types[type_name]

    def list_types(self) -> List[str]:
        """List all registered plugin type names."""
        return list(self._types.keys())

    def get_all_types(self) -> List[PluginType]:
        """Get all registered plugin types."""
        return list(self._types.values())


# Global singleton
_type_registry: Optional[PluginTypeRegistry] = None


def get_type_registry() -> PluginTypeRegistry:
    """Get the global plugin type registry."""
    global _type_registry
    if _type_registry is None:
        _type_registry = PluginTypeRegistry()
    return _type_registry
```

### Plugin Type Discovery

Plugin types are themselves discovered via entry points, enabling third parties to create entirely new plugin categories.

**Entry Point Group**: `infrafoundry.plugin_types`

**Built-in Plugin Types** (ship with infrafoundry-core):

```toml
# infrafoundry-core/pyproject.toml
[project.entry-points."infrafoundry.plugin_types"]
provider = "infrafoundry.providers.plugin_type:ProviderPluginType"
secret_backend = "infrafoundry.secrets.plugin_type:SecretBackendPluginType"
```

**Third-Party Plugin Types** (future):

```toml
# infrafoundry-workflow-plugin-type/pyproject.toml
[project.entry-points."infrafoundry.plugin_types"]
workflow = "infrafoundry_workflow_type:WorkflowPluginType"
```

**Discovery at Startup**:

```python
from importlib.metadata import entry_points
from infrafoundry.core.plugin_system import get_type_registry

# Discover all plugin types
type_registry = get_type_registry()
plugin_type_eps = entry_points(group="infrafoundry.plugin_types")

for ep in plugin_type_eps:
    plugin_type_class = ep.load()  # Load the PluginType class
    plugin_type = plugin_type_class()  # Instantiate it
    type_registry.register_type(plugin_type)
    logger.info(f"Registered plugin type: {plugin_type.type_name}")
```

**Benefits**:
- Built-in types use the same mechanism as third-party types
- No hard-coding of plugin types in core
- Third parties can create entirely new plugin categories
- Plugin types are as extensible as plugins themselves

---

## Entry Points Mechanism

### How Entry Points Work

Entry points are Python's standard plugin mechanism (PEP 621). Packages declare entry points in their metadata, and other packages can discover them.

### Entry Point Groups

**Plugin Types** declare themselves:

| Entry Point Group | Purpose | Examples |
|------------------|---------|----------|
| `infrafoundry.plugin_types` | Register plugin types | `provider`, `secret_backend`, `reporter` |

**Plugins** declare themselves under type-specific groups:

| Plugin Type | Entry Point Group | Example Plugins |
|-------------|-------------------|----------------|
| Plugin Types | `infrafoundry.plugin_types` | `provider`, `secret_backend`, `reporter` |
| Providers | `infrafoundry.providers` | `proxmox`, `aws`, `lxd` |
| Secret Backends | `infrafoundry.secrets` | `env`, `file`, `vault`, `aws` |
| Reporters | `infrafoundry.reporters` | `pdf`, `html`, `grafana` |
| Analyzers | `infrafoundry.analyzers` | `cost`, `security`, `compliance` |
| Exporters | `infrafoundry.exporters` | `confluence`, `wiki`, `markdown` |
| Hooks | `infrafoundry.hooks` | `slack-notify`, `email-alert` |

### Plugin Declaration

**Plugin Type Declaration** (register a new plugin type):

```toml
# infrafoundry-core/pyproject.toml (built-in types)
[project.entry-points."infrafoundry.plugin_types"]
provider = "infrafoundry.providers.plugin_type:ProviderPluginType"
secret_backend = "infrafoundry.secrets.plugin_type:SecretBackendPluginType"
```

**Plugin Declarations** (plugins of specific types):

**Provider Plugin:**
```toml
# infrafoundry-proxmox/pyproject.toml
[project.entry-points."infrafoundry.providers"]
proxmox = "infrafoundry_proxmox:register"
```

**Secret Backend Plugin:**
```toml
# infrafoundry-vault-secrets/pyproject.toml
[project.entry-points."infrafoundry.secrets"]
vault = "infrafoundry_vault_secrets:register"
```

**Reporter Plugin:**
```toml
# infrafoundry-pdf-reporter/pyproject.toml
[project.entry-points."infrafoundry.reporters"]
pdf = "infrafoundry_pdf_reporter:register"
```

**Analyzer Plugin:**
```toml
# infrafoundry-cost-analyzer/pyproject.toml
[project.entry-points."infrafoundry.analyzers"]
cost = "infrafoundry_cost_analyzer:register"
```

---

## Plugin Discovery

### Generic Discovery Engine

The discovery engine is **completely type-agnostic**:

**File**: `src/infrafoundry/core/plugin_system/discovery.py`

```python
"""Generic plugin discovery."""

from importlib.metadata import entry_points
from typing import List
import logging

from infrafoundry.core.plugin_system.plugin_type import (
    PluginType,
    PluginMetadata,
)
from infrafoundry.core.plugin_system.exceptions import PluginLoadError


logger = logging.getLogger(__name__)


class PluginDiscovery:
    """Generic plugin discovery engine."""

    def discover_plugins(self, plugin_type: PluginType) -> List[PluginMetadata]:
        """
        Discover all plugins for a given plugin type.

        Args:
            plugin_type: Plugin type to discover plugins for

        Returns:
            List of discovered plugin metadata
        """
        discovered = []
        group = plugin_type.entry_point_group

        logger.info(f"Discovering plugins for '{plugin_type.type_name}' (group: {group})")

        # Get all entry points for this group
        eps = entry_points(group=group)

        for ep in eps:
            try:
                # Let the plugin type load and validate the plugin
                metadata = plugin_type.load_plugin(ep)

                # Validate the plugin
                validation = plugin_type.validate_plugin(metadata)

                if not validation.valid:
                    logger.error(
                        f"Plugin {ep.name} validation failed: {validation.errors}"
                    )
                    continue

                if validation.warnings:
                    for warning in validation.warnings:
                        logger.warning(f"Plugin {ep.name}: {warning}")

                discovered.append(metadata)
                logger.info(
                    f"Discovered plugin: {ep.name} "
                    f"({plugin_type.type_name}) v{metadata.version}"
                )

            except PluginLoadError as e:
                logger.error(f"Failed to load plugin {ep.name}: {e}")
                continue
            except Exception as e:
                logger.error(f"Unexpected error loading plugin {ep.name}: {e}")
                continue

        logger.info(
            f"Discovered {len(discovered)} {plugin_type.type_name} plugin(s)"
        )
        return discovered

    def discover_all(self, plugin_types: List[PluginType]) -> Dict[str, List[PluginMetadata]]:
        """
        Discover plugins for all plugin types.

        Args:
            plugin_types: List of plugin types to discover

        Returns:
            Dict mapping plugin type name to list of plugins
        """
        all_plugins = {}

        for plugin_type in plugin_types:
            plugins = self.discover_plugins(plugin_type)
            all_plugins[plugin_type.type_name] = plugins

        return all_plugins
```

### Discovery Process

```
1. Core gets all registered plugin types
2. For each plugin type:
   a. Get entry point group from plugin type
   b. Scan entry points for that group
   c. For each entry point:
      - Call plugin_type.load_plugin(entry_point)
      - Call plugin_type.validate_plugin(metadata)
      - If valid, add to discovered plugins
3. Return discovered plugins grouped by type
```

**Key Insight**: Discovery doesn't know about providers, reporters, etc. It just asks plugin types to load and validate their plugins.

---

## Plugin Registry

### Generic Registry

The registry stores plugins of **any type**:

**File**: `src/infrafoundry/core/plugin_system/registry.py`

```python
"""Generic plugin registry."""

from typing import Dict, List, Optional
import logging

from infrafoundry.core.plugin_system.plugin_type import PluginMetadata
from infrafoundry.core.plugin_system.exceptions import (
    PluginNotFoundError,
    PluginAlreadyRegisteredError,
)


logger = logging.getLogger(__name__)


class PluginRegistry:
    """Generic registry for all plugins."""

    def __init__(self):
        # Storage: {plugin_type: {plugin_name: PluginMetadata}}
        self._plugins: Dict[str, Dict[str, PluginMetadata]] = {}

    def register(self, metadata: PluginMetadata) -> None:
        """
        Register a plugin.

        Args:
            metadata: Plugin metadata

        Raises:
            PluginAlreadyRegisteredError: If plugin already registered
        """
        plugin_type = metadata.plugin_type
        plugin_name = metadata.name

        # Initialize type category if needed
        if plugin_type not in self._plugins:
            self._plugins[plugin_type] = {}

        # Check for duplicates
        if plugin_name in self._plugins[plugin_type]:
            raise PluginAlreadyRegisteredError(
                f"Plugin '{plugin_name}' ({plugin_type}) already registered"
            )

        self._plugins[plugin_type][plugin_name] = metadata
        logger.info(f"Registered plugin: {plugin_name} ({plugin_type}) v{metadata.version}")

    def get(self, plugin_type: str, plugin_name: str) -> PluginMetadata:
        """
        Get a plugin by type and name.

        Args:
            plugin_type: Plugin type (e.g., "provider")
            plugin_name: Plugin name (e.g., "proxmox")

        Returns:
            Plugin metadata

        Raises:
            PluginNotFoundError: If plugin not found
        """
        if plugin_type not in self._plugins:
            raise PluginNotFoundError(
                f"No plugins of type '{plugin_type}' registered"
            )

        if plugin_name not in self._plugins[plugin_type]:
            raise PluginNotFoundError(
                f"Plugin '{plugin_name}' ({plugin_type}) not found"
            )

        return self._plugins[plugin_type][plugin_name]

    def list_by_type(self, plugin_type: str) -> List[PluginMetadata]:
        """
        List all plugins of a specific type.

        Args:
            plugin_type: Plugin type to list

        Returns:
            List of plugin metadata
        """
        if plugin_type not in self._plugins:
            return []

        return list(self._plugins[plugin_type].values())

    def list_all(self) -> Dict[str, List[PluginMetadata]]:
        """
        List all plugins grouped by type.

        Returns:
            Dict mapping plugin type to list of plugins
        """
        return {
            plugin_type: list(plugins.values())
            for plugin_type, plugins in self._plugins.items()
        }

    def has_plugin(self, plugin_type: str, plugin_name: str) -> bool:
        """Check if a plugin is registered."""
        return (
            plugin_type in self._plugins
            and plugin_name in self._plugins[plugin_type]
        )


# Global singleton
_registry: Optional[PluginRegistry] = None


def get_registry() -> PluginRegistry:
    """Get the global plugin registry."""
    global _registry
    if _registry is None:
        _registry = PluginRegistry()
    return _registry
```

### Registry Operations

```python
# Register plugins
registry.register(proxmox_metadata)
registry.register(pdf_reporter_metadata)
registry.register(cost_analyzer_metadata)

# Get specific plugin
proxmox = registry.get("provider", "proxmox")
pdf_reporter = registry.get("reporter", "pdf")

# List by type
all_providers = registry.list_by_type("provider")
all_reporters = registry.list_by_type("reporter")

# List all
all_plugins = registry.list_all()
# {"provider": [...], "reporter": [...], "analyzer": [...]}
```

---

## Plugin Lifecycle

### Initialization Sequence

```
1. InfraFoundry Core Startup
   ↓
2. Initialize Plugin Type Registry
   ↓
3. Discover Plugin Types
   - Scan entry points for "infrafoundry.plugin_types"
   - Load PluginType classes
   - Instantiate and register them
   - Built-in types: ProviderPluginType, SecretBackendPluginType
   - Third-party types: WorkflowPluginType, etc.
   ↓
4. Initialize Plugin Discovery
   ↓
5. Discover Plugins for Each Type
   - For each registered plugin type:
     - Scan entry points for that type's group
     - Load plugins
     - Validate plugins
   ↓
6. Register Plugins in Plugin Registry
   ↓
7. CLI Integration
   - For each plugin type:
     - Call plugin_type.register_cli(app, plugins)
   ↓
8. Ready for Use
```

### Bootstrap Code

**File**: `src/infrafoundry/core/plugin_system/__init__.py`

```python
"""Plugin system initialization."""

from importlib.metadata import entry_points
from infrafoundry.core.plugin_system.plugin_type_registry import (
    get_type_registry,
)
from infrafoundry.core.plugin_system.discovery import PluginDiscovery
from infrafoundry.core.plugin_system.registry import get_registry
import logging


logger = logging.getLogger(__name__)


def initialize_plugin_system():
    """Initialize the plugin system."""

    # Step 1: Initialize registries
    type_registry = get_type_registry()
    plugin_registry = get_registry()
    discovery = PluginDiscovery()

    # Step 2: Discover and register plugin types
    logger.info("Discovering plugin types...")
    plugin_type_eps = entry_points(group="infrafoundry.plugin_types")

    for ep in plugin_type_eps:
        try:
            plugin_type_class = ep.load()
            plugin_type = plugin_type_class()
            type_registry.register_type(plugin_type)
            logger.info(f"Registered plugin type: {plugin_type.type_name}")
        except Exception as e:
            logger.error(f"Failed to register plugin type {ep.name}: {e}")
            continue

    # Step 3: Discover plugins for all registered types
    logger.info("Discovering plugins...")
    plugin_types = type_registry.get_all_types()
    discovered = discovery.discover_all(plugin_types)

    # Step 4: Register discovered plugins
    for plugin_type_name, plugins in discovered.items():
        for plugin_metadata in plugins:
            plugin_registry.register(plugin_metadata)

    logger.info("Plugin system initialized")
    return plugin_registry
```

### Plugin Instantiation

Plugins are discovered and registered at startup, but **not instantiated** until needed:

- **Discovery**: Scan entry points, call `register()` functions
- **Registration**: Store metadata in registry
- **Instantiation**: Create plugin instance when actually used (lazy)

---

## Error Handling

### Exception Hierarchy

**File**: `src/infrafoundry/core/plugin_system/exceptions.py`

```python
"""Plugin system exceptions."""


class PluginSystemError(Exception):
    """Base exception for plugin system."""


# Plugin Type Errors
class PluginTypeError(PluginSystemError):
    """Plugin type error."""


class PluginTypeNotFound(PluginTypeError):
    """Plugin type not registered."""


class PluginTypeAlreadyRegistered(PluginTypeError):
    """Plugin type already registered."""


# Plugin Errors
class PluginError(PluginSystemError):
    """Plugin error."""


class PluginNotFoundError(PluginError):
    """Plugin not found in registry."""


class PluginAlreadyRegisteredError(PluginError):
    """Plugin already registered."""


class PluginLoadError(PluginError):
    """Failed to load plugin."""


class PluginValidationError(PluginError):
    """Plugin validation failed."""
```

### Error Handling Strategy

| Error | Strategy | User Impact |
|-------|----------|-------------|
| Plugin type not found | Fail startup | Clear error message |
| Entry point load fails | Log warning, skip plugin | Plugin unavailable |
| Plugin validation fails | Log error, skip plugin | Plugin unavailable |
| Duplicate plugin | Log error, use first/newest | One version available |
| Plugin runtime error | Raise to caller | Clear error to user |

### Graceful Degradation

A single broken plugin should **not** crash InfraFoundry:

```python
# Discovery continues even if one plugin fails
try:
    metadata = plugin_type.load_plugin(ep)
except Exception as e:
    logger.error(f"Failed to load {ep.name}: {e}")
    continue  # Skip this plugin, continue with others
```

---

## Provider Plugin Type

### Provider-Specific Implementation

Providers are ONE specific plugin type. The provider plugin type defines:

**File**: `src/infrafoundry/providers/plugin_type.py`

```python
"""Provider plugin type implementation."""

from typing import Any, List
import logging

from infrafoundry.core.plugin_system.plugin_type import (
    PluginType,
    PluginMetadata,
    ValidationResult,
)
from infrafoundry.providers.protocol import BaseProvider


logger = logging.getLogger(__name__)


class ProviderPluginType(PluginType):
    """Provider plugin type."""

    @property
    def entry_point_group(self) -> str:
        return "infrafoundry.providers"

    @property
    def type_name(self) -> str:
        return "provider"

    def load_plugin(self, entry_point) -> PluginMetadata:
        """Load a provider plugin."""
        # Load the registration function
        register_func = entry_point.load()

        # Call it to get provider metadata
        provider_metadata = register_func()

        # Convert to generic PluginMetadata
        return PluginMetadata(
            name=provider_metadata.name,
            version=provider_metadata.version,
            plugin_type="provider",
            description=provider_metadata.description,
            implementation=provider_metadata.provider_class,
            metadata={
                "resource_types": provider_metadata.resource_types,
                "cli_registration": provider_metadata.cli_registration,
                "author": provider_metadata.author,
                "url": provider_metadata.url,
            }
        )

    def validate_plugin(self, metadata: PluginMetadata) -> ValidationResult:
        """Validate provider implements BaseProvider protocol."""
        errors = []
        warnings = []

        provider_class = metadata.implementation

        # Check required methods
        required_methods = [
            "create", "read", "update", "delete",
            "list_resources", "validate_config"
        ]

        for method in required_methods:
            if not hasattr(provider_class, method):
                errors.append(f"Missing required method: {method}")

        # Check resource types
        resource_types = metadata.metadata.get("resource_types", [])
        if not resource_types:
            warnings.append("No resource types declared")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def register_cli(self, app: Any, plugins: List[PluginMetadata]) -> None:
        """Register provider CLI commands."""
        import click

        for plugin in plugins:
            # Create provider group (e.g., "foundry proxmox")
            provider_group = click.Group(
                name=plugin.name,
                help=plugin.description,
            )
            app.add_command(provider_group)

            # Let provider register its commands
            cli_registration = plugin.metadata.get("cli_registration")
            if cli_registration:
                cli_registration(provider_group)
```

### Provider Protocol

**File**: `src/infrafoundry/providers/protocol.py`

```python
"""Provider protocol."""

from typing import Protocol, Dict, Any, List
from abc import abstractmethod


class BaseProvider(Protocol):
    """Protocol that all providers must implement."""

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize provider with configuration."""

    @abstractmethod
    def create(
        self,
        resource_type: str,
        resource_config: Dict[str, Any]
    ) -> ResourceResult:
        """Create a resource."""

    @abstractmethod
    def read(
        self,
        resource_type: str,
        resource_id: str
    ) -> ResourceResult:
        """Read resource state."""

    @abstractmethod
    def update(
        self,
        resource_type: str,
        resource_id: str,
        desired_config: Dict[str, Any]
    ) -> ResourceResult:
        """Update a resource."""

    @abstractmethod
    def delete(
        self,
        resource_type: str,
        resource_id: str
    ) -> None:
        """Delete a resource."""

    @abstractmethod
    def list_resources(
        self,
        resource_type: str
    ) -> List[ResourceSummary]:
        """List resources."""

    @abstractmethod
    def validate_config(
        self,
        resource_type: str,
        resource_config: Dict[str, Any]
    ) -> ValidationResult:
        """Validate configuration."""
```

### Provider-Specific Registry Operations

Providers might need specialized registry operations:

**File**: `src/infrafoundry/providers/registry.py`

```python
"""Provider-specific registry operations."""

from infrafoundry.core.plugin_system import get_registry


class ProviderRegistry:
    """Provider-specific registry operations."""

    def __init__(self):
        self._core_registry = get_registry()

    def get_provider_metadata(self, name: str):
        """Get provider metadata."""
        return self._core_registry.get("provider", name)

    def get_provider_class(self, name: str):
        """Get provider class."""
        metadata = self.get_provider_metadata(name)
        return metadata.implementation

    def create_provider(self, name: str, config: Dict[str, Any]):
        """Instantiate a provider."""
        provider_class = self.get_provider_class(name)
        return provider_class(config)

    def list_providers(self) -> List[str]:
        """List all provider names."""
        providers = self._core_registry.list_by_type("provider")
        return [p.name for p in providers]

    def get_resource_types(self, provider_name: str) -> List[str]:
        """Get resource types for a provider."""
        metadata = self.get_provider_metadata(provider_name)
        return metadata.metadata.get("resource_types", [])
```

---

## Built-in Plugin Types

InfraFoundry core ships with two built-in plugin types that form the foundation of the system.

### 1. Provider Plugin Type

See the [Provider Plugin Type](#provider-plugin-type) section above for full details.

**Purpose**: Manage infrastructure resources (VMs, containers, cloud instances, etc.)

**Entry Point Group**: `infrafoundry.providers`

**Protocol**: `BaseProvider`

**Built-in Providers** (bundled with infrafoundry):
- `proxmox` - Proxmox Virtual Environment
- `lxd` - LXD containers
- `terraform` - Terraform resources

### 2. Secret Backend Plugin Type

See [SECRET_BACKEND_DESIGN.md](./SECRET_BACKEND_DESIGN.md) for full details.

**Purpose**: Manage secrets and sensitive configuration (API tokens, passwords, certificates, etc.)

**Entry Point Group**: `infrafoundry.secrets`

**Protocol**: `SecretBackend`

**Built-in Backends** (ship with core):
- `env` - Environment variables (default)
- `file` - JSON file storage

**Third-Party Backends** (community):
- `vault` - HashiCorp Vault
- `aws` - AWS Secrets Manager
- `azure` - Azure Key Vault

**Why Secret Backend is Built-in**:
- Secrets are required by providers (API credentials)
- Cross-cutting concern for all infrastructure
- Must work out of the box (env backend)
- Foundation for secure configuration management

**Integration with Providers**:
```yaml
# Configuration references secrets
providers:
  proxmox:
    token_value: "secret://proxmox/token"

# Secret backend resolves references
secrets:
  backend: vault  # or env, file, aws, etc.
  config:
    url: "https://vault.example.com"
```

Providers receive resolved secrets at instantiation time.

---

## Future Plugin Types

### Reporter Plugin Type

**File**: `src/infrafoundry/reporters/plugin_type.py`

```python
"""Reporter plugin type."""

from infrafoundry.core.plugin_system.plugin_type import PluginType


class ReporterPluginType(PluginType):
    """Reporter plugin type for custom output formats."""

    @property
    def entry_point_group(self) -> str:
        return "infrafoundry.reporters"

    @property
    def type_name(self) -> str:
        return "reporter"

    def load_plugin(self, entry_point):
        # Load reporter registration function
        pass

    def validate_plugin(self, metadata):
        # Validate implements BaseReporter protocol
        pass

    def register_cli(self, app, plugins):
        # Add --format options to commands
        pass
```

**Reporter Protocol:**
```python
class BaseReporter(Protocol):
    """Protocol for reporter plugins."""

    def generate_report(
        self,
        data: Any,
        output_path: Optional[str] = None
    ) -> bytes:
        """Generate report from data."""
```

**Example Reporter Plugins:**
- `infrafoundry-pdf-reporter` - PDF reports
- `infrafoundry-html-reporter` - HTML dashboards
- `infrafoundry-grafana-reporter` - Grafana integration

### Analyzer Plugin Type

**File**: `src/infrafoundry/analyzers/plugin_type.py`

```python
"""Analyzer plugin type."""

class AnalyzerPluginType(PluginType):
    """Analyzer plugin type for custom analysis tools."""

    @property
    def entry_point_group(self) -> str:
        return "infrafoundry.analyzers"

    @property
    def type_name(self) -> str:
        return "analyzer"
```

**Analyzer Protocol:**
```python
class BaseAnalyzer(Protocol):
    """Protocol for analyzer plugins."""

    def analyze(
        self,
        resources: List[Resource],
        config: Dict[str, Any]
    ) -> AnalysisResult:
        """Analyze resources."""
```

**Example Analyzer Plugins:**
- `infrafoundry-cost-analyzer` - Cost analysis
- `infrafoundry-security-analyzer` - Security audit
- `infrafoundry-compliance-analyzer` - Compliance checking

### Exporter Plugin Type

**Exporter Protocol:**
```python
class BaseExporter(Protocol):
    """Protocol for exporter plugins."""

    def export(
        self,
        state: StateFile,
        destination: str,
        config: Dict[str, Any]
    ) -> None:
        """Export state to destination."""
```

**Example Exporter Plugins:**
- `infrafoundry-confluence-exporter` - Confluence pages
- `infrafoundry-wiki-exporter` - Wiki documentation
- `infrafoundry-markdown-exporter` - Markdown docs

### Hook Plugin Type

**Hook Protocol:**
```python
class BaseHook(Protocol):
    """Protocol for hook plugins."""

    def on_pre_apply(self, context: HookContext) -> None:
        """Called before apply."""

    def on_post_apply(self, context: HookContext, result: Any) -> None:
        """Called after apply."""

    def on_error(self, context: HookContext, error: Exception) -> None:
        """Called on error."""
```

**Example Hook Plugins:**
- `infrafoundry-slack-hook` - Slack notifications
- `infrafoundry-email-hook` - Email alerts
- `infrafoundry-approval-hook` - Manual approval workflow

---

## Implementation Roadmap

### Phase 1: Generic Infrastructure (Week 1-2)

- [ ] Define `PluginType` protocol
- [ ] Implement `PluginTypeRegistry`
- [ ] Implement plugin type discovery (scan `infrafoundry.plugin_types`)
- [ ] Implement generic `PluginDiscovery`
- [ ] Implement generic `PluginRegistry`
- [ ] Define exception hierarchy
- [ ] Write unit tests for generic infrastructure

### Phase 2: Built-in Plugin Types (Week 2-3)

**Provider Plugin Type:**
- [ ] Define `BaseProvider` protocol
- [ ] Implement `ProviderPluginType`
- [ ] Implement `ProviderRegistry` (specialized operations)
- [ ] Declare entry point for provider plugin type
- [ ] Write tests for provider plugin type

**Secret Backend Plugin Type:**
- [ ] Define `SecretBackend` protocol
- [ ] Implement `SecretBackendPluginType`
- [ ] Implement `EnvSecretBackend` (default)
- [ ] Implement `FileSecretBackend`
- [ ] Implement secret resolution system
- [ ] Declare entry point for secret backend plugin type
- [ ] Write tests for secret backends

**Integration:**
- [ ] Test plugin type discovery
- [ ] Verify both plugin types registered
- [ ] Integration tests

### Phase 3: Extract Proxmox Provider (Week 3-4)

- [ ] Create `infrafoundry-proxmox` package structure
- [ ] Move Proxmox code to new package
- [ ] Implement `register()` function
- [ ] Add entry point to `pyproject.toml`
- [ ] Test discovery and registration
- [ ] Verify CLI integration works

### Phase 4: Validation & Documentation (Week 4-5)

- [ ] Integration tests
- [ ] End-to-end testing
- [ ] Developer documentation
- [ ] Plugin authoring guide
- [ ] Example third-party plugin

### Phase 5: Extract Remaining Providers (Week 5-6)

- [ ] Extract LXD provider
- [ ] Extract Terraform provider
- [ ] Bundle in meta-package
- [ ] Final testing

### Future Phases

- Implement reporter plugin type
- Implement analyzer plugin type
- Implement exporter plugin type
- Implement hook plugin type
- Third-party plugin ecosystem

---

## Package Structure

### Monorepo Layout

```
infrafoundry/
├── packages/
│   ├── infrafoundry-core/
│   │   ├── src/
│   │   │   └── infrafoundry/
│   │   │       └── core/
│   │   │           └── plugin_system/        # Generic infrastructure
│   │   │               ├── __init__.py
│   │   │               ├── plugin_type.py    # PluginType protocol
│   │   │               ├── plugin_type_registry.py
│   │   │               ├── discovery.py      # Generic discovery
│   │   │               ├── registry.py       # Generic registry
│   │   │               ├── lifecycle.py
│   │   │               └── exceptions.py
│   │   │
│   │   ├── src/
│   │   │   └── infrafoundry/
│   │   │       ├── providers/                # Provider plugin type
│   │   │       │   ├── __init__.py
│   │   │       │   ├── plugin_type.py        # ProviderPluginType
│   │   │       │   ├── protocol.py           # BaseProvider
│   │   │       │   └── registry.py           # Provider registry ops
│   │   │       │
│   │   │       └── secrets/                  # Secret backend plugin type
│   │   │           ├── __init__.py
│   │   │           ├── plugin_type.py        # SecretBackendPluginType
│   │   │           ├── protocol.py           # SecretBackend
│   │   │           ├── env_backend.py        # Environment variable backend
│   │   │           ├── file_backend.py       # File-based backend
│   │   │           └── exceptions.py         # Secret-specific exceptions
│   │
│   ├── infrafoundry-proxmox/                 # Provider plugin
│   │   └── ... (see PROXMOX_PROVIDER_DESIGN.md)
│   │
│   ├── infrafoundry-lxd/                     # Provider plugin
│   ├── infrafoundry-terraform/               # Provider plugin
│   │
│   └── infrafoundry/                         # Meta-package (bundles all)
│       └── pyproject.toml
```

---

## Success Criteria

- [ ] Generic plugin system knows nothing about specific plugin types
- [ ] New plugin types can be added without modifying core
- [ ] Plugins auto-discovered via entry points
- [ ] Multiple plugin types can coexist
- [ ] Clear separation: infrastructure → plugin types → plugins
- [ ] Third parties can create plugin types AND plugins
- [ ] Comprehensive tests for generic infrastructure
- [ ] Documentation for adding new plugin types

---

## Open Questions

1. **Plugin Type as Plugin**: Should plugin types themselves be discoverable via entry points?
2. **Version Compatibility**: How to handle core/plugin type/plugin version compatibility?
3. **Plugin Dependencies**: How do we handle plugin A depending on plugin B?
4. **CLI Namespacing**: Should plugin types control their CLI namespace?
5. **Configuration Schema**: Should plugin types define config validation?
6. **State Format**: How do different plugin types integrate with state?

---

## Conclusion

This design provides a **truly generic plugin architecture** where:

1. **Core is type-agnostic**: Generic discovery, registry, and lifecycle
2. **Plugin types are first-class**: Define their own protocols and operations
3. **Plugins are isolated**: Each is a separate package
4. **System is extensible**: New plugin types can be added without core changes
5. **Third parties empowered**: Can create both plugin types and plugins

The provider plugin type is just the first implementation - reporters, analyzers, exporters, and hooks will follow the same pattern.
