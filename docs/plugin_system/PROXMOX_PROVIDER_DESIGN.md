# Proxmox Provider Plugin Design

**Version:** 1.0
**Date:** 2025-12-28
**Status:** Design Phase
**Related:** [Plugin System Design](./PLUGIN_SYSTEM_DESIGN.md)

## Table of Contents

1. [Overview](#overview)
2. [Package Structure](#package-structure)
3. [Registration Function](#registration-function)
4. [Provider Implementation](#provider-implementation)
5. [CLI Integration](#cli-integration)
6. [Configuration](#configuration)
7. [Resource Types](#resource-types)
8. [API Client Layer](#api-client-layer)
9. [Error Handling](#error-handling)
10. [Testing Strategy](#testing-strategy)
11. [Migration Plan](#migration-plan)
12. [Dependencies](#dependencies)

---

## Overview

### Goal

Extract the Proxmox provider from InfraFoundry core into a standalone plugin package that:
- Implements the provider plugin protocol
- Registers via entry points
- Can be installed/uninstalled independently
- Maintains all existing functionality
- Serves as reference implementation for other providers

### Current State

Proxmox provider currently lives in:
- `src/infrafoundry/providers/proxmox/` - Provider implementation
- `src/infrafoundry/cli/commands/proxmox_*.py` - CLI commands
- Tests scattered across test files

### Target State

Proxmox provider as standalone package:
- Package name: `infrafoundry-proxmox`
- Entry point: `proxmox = "infrafoundry_proxmox:register"`
- Self-contained with all code, tests, and dependencies
- Installable via: `uv pip install infrafoundry-proxmox`

---

## Package Structure

### Directory Layout

```
packages/infrafoundry-proxmox/
├── src/
│   └── infrafoundry_proxmox/
│       ├── __init__.py              # Public API + register()
│       ├── provider.py              # ProxmoxProvider class
│       ├── cli.py                   # CLI registration
│       ├── config.py                # Configuration models
│       ├── exceptions.py            # Proxmox-specific exceptions
│       │
│       ├── api/                     # Proxmox API client layer
│       │   ├── __init__.py
│       │   ├── client.py           # ProxmoxClient wrapper
│       │   ├── vm.py               # VM operations
│       │   ├── container.py        # Container operations
│       │   ├── snapshot.py         # Snapshot operations
│       │   └── storage.py          # Storage operations
│       │
│       ├── resources/              # Resource type implementations
│       │   ├── __init__.py
│       │   ├── base.py            # Base resource class
│       │   ├── vm.py              # VM resource handler
│       │   ├── container.py       # Container resource handler
│       │   └── snapshot.py        # Snapshot resource handler
│       │
│       └── utils/                  # Utilities
│           ├── __init__.py
│           ├── validators.py      # Config validators
│           └── formatters.py      # Output formatters
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                # Pytest fixtures
│   ├── test_provider.py           # Provider tests
│   ├── test_cli.py                # CLI tests
│   ├── test_resources/
│   │   ├── test_vm.py
│   │   ├── test_container.py
│   │   └── test_snapshot.py
│   └── test_api/
│       ├── test_client.py
│       └── test_vm.py
│
├── docs/
│   ├── README.md                  # Provider documentation
│   ├── configuration.md           # Config guide
│   └── examples.md                # Usage examples
│
├── pyproject.toml                 # Package metadata + entry point
├── README.md                      # Package README
└── LICENSE                        # License file
```

### Key Design Decisions

1. **Namespace**: `infrafoundry_proxmox` (underscore, not dash)
   - Importable as Python module
   - Clear separation from core

2. **Layered Architecture**:
   - `api/` - Raw Proxmox API interactions
   - `resources/` - Resource type handlers (business logic)
   - `provider.py` - Provider interface implementation
   - `cli.py` - CLI commands

3. **Self-Contained**: All Proxmox-specific code in this package
   - No Proxmox logic in core
   - Provider owns its complete domain

---

## Registration Function

### Implementation

**File**: `src/infrafoundry_proxmox/__init__.py`

```python
"""Proxmox provider plugin for InfraFoundry."""

from infrafoundry.core.plugin_system import ProviderMetadata
from infrafoundry_proxmox.provider import ProxmoxProvider
from infrafoundry_proxmox.cli import register_cli

__version__ = "0.1.0"

def register() -> ProviderMetadata:
    """
    Register the Proxmox provider plugin.

    Called by InfraFoundry core during plugin discovery.

    Returns:
        ProviderMetadata with provider information
    """
    return ProviderMetadata(
        name="proxmox",
        version=__version__,
        provider_class=ProxmoxProvider,
        description="Proxmox Virtual Environment provider",
        resource_types=["vm", "container", "snapshot", "storage"],
        cli_registration=register_cli,
        author="InfraFoundry Team",
        url="https://github.com/infrafoundry/infrafoundry-proxmox",
        requires_core_version=">=0.1.0,<1.0.0",
    )

# Public API
__all__ = [
    "register",
    "ProxmoxProvider",
    "__version__",
]
```

### Entry Point Declaration

**File**: `pyproject.toml`

```toml
[project.entry-points."infrafoundry.providers"]
proxmox = "infrafoundry_proxmox:register"
```

### What Happens

1. Core scans entry points for `infrafoundry.providers`
2. Finds `proxmox` entry point
3. Loads `infrafoundry_proxmox:register`
4. Calls `register()` function
5. Receives `ProviderMetadata`
6. Stores in provider registry
7. Calls `register_cli()` if needed

---

## Provider Implementation

### Provider Class

**File**: `src/infrafoundry_proxmox/provider.py`

```python
"""Proxmox provider implementation."""

from typing import Any, Dict, List
from infrafoundry.core.plugin_system import (
    BaseProvider,
    ResourceResult,
    ValidationResult,
    ResourceSummary,
)
from infrafoundry_proxmox.config import ProxmoxConfig
from infrafoundry_proxmox.api import ProxmoxClient
from infrafoundry_proxmox.resources import (
    VMResource,
    ContainerResource,
    SnapshotResource,
)
from infrafoundry_proxmox.exceptions import ProxmoxProviderError


class ProxmoxProvider(BaseProvider):
    """Proxmox Virtual Environment provider."""

    def __init__(self, config: Dict[str, Any]) -> None:
        """
        Initialize Proxmox provider.

        Args:
            config: Provider configuration dict

        Raises:
            ProxmoxProviderError: If configuration invalid or connection fails
        """
        self.config = ProxmoxConfig.from_dict(config)
        self.client = ProxmoxClient(
            host=self.config.host,
            user=self.config.user,
            token_name=self.config.token_name,
            token_value=self.config.token_value,
            verify_ssl=self.config.verify_ssl,
        )

        # Resource handlers
        self._resource_handlers = {
            "vm": VMResource(self.client),
            "container": ContainerResource(self.client),
            "snapshot": SnapshotResource(self.client),
        }

        # Validate connection
        self._validate_connection()

    def _validate_connection(self) -> None:
        """Validate connection to Proxmox API."""
        try:
            self.client.version()
        except Exception as e:
            raise ProxmoxProviderError(
                f"Failed to connect to Proxmox: {e}"
            ) from e

    def _get_handler(self, resource_type: str):
        """Get resource handler for type."""
        if resource_type not in self._resource_handlers:
            raise ProxmoxProviderError(
                f"Unsupported resource type: {resource_type}"
            )
        return self._resource_handlers[resource_type]

    def create(
        self,
        resource_type: str,
        resource_config: Dict[str, Any]
    ) -> ResourceResult:
        """Create a Proxmox resource."""
        handler = self._get_handler(resource_type)
        return handler.create(resource_config)

    def read(
        self,
        resource_type: str,
        resource_id: str
    ) -> ResourceResult:
        """Read Proxmox resource state."""
        handler = self._get_handler(resource_type)
        return handler.read(resource_id)

    def update(
        self,
        resource_type: str,
        resource_id: str,
        desired_config: Dict[str, Any]
    ) -> ResourceResult:
        """Update Proxmox resource."""
        handler = self._get_handler(resource_type)
        return handler.update(resource_id, desired_config)

    def delete(
        self,
        resource_type: str,
        resource_id: str
    ) -> None:
        """Delete Proxmox resource."""
        handler = self._get_handler(resource_type)
        handler.delete(resource_id)

    def list_resources(
        self,
        resource_type: str
    ) -> List[ResourceSummary]:
        """List Proxmox resources."""
        handler = self._get_handler(resource_type)
        return handler.list()

    def validate_config(
        self,
        resource_type: str,
        resource_config: Dict[str, Any]
    ) -> ValidationResult:
        """Validate resource configuration."""
        handler = self._get_handler(resource_type)
        return handler.validate_config(resource_config)
```

### Resource Handler Base Class

**File**: `src/infrafoundry_proxmox/resources/base.py`

```python
"""Base resource handler."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List
from infrafoundry.core.plugin_system import (
    ResourceResult,
    ValidationResult,
    ResourceSummary,
)


class BaseResourceHandler(ABC):
    """Base class for resource type handlers."""

    def __init__(self, client):
        """Initialize with Proxmox client."""
        self.client = client

    @abstractmethod
    def create(self, config: Dict[str, Any]) -> ResourceResult:
        """Create resource."""

    @abstractmethod
    def read(self, resource_id: str) -> ResourceResult:
        """Read resource state."""

    @abstractmethod
    def update(
        self,
        resource_id: str,
        config: Dict[str, Any]
    ) -> ResourceResult:
        """Update resource."""

    @abstractmethod
    def delete(self, resource_id: str) -> None:
        """Delete resource."""

    @abstractmethod
    def list(self) -> List[ResourceSummary]:
        """List all resources."""

    @abstractmethod
    def validate_config(self, config: Dict[str, Any]) -> ValidationResult:
        """Validate configuration."""
```

### VM Resource Handler Example

**File**: `src/infrafoundry_proxmox/resources/vm.py`

```python
"""VM resource handler."""

from typing import Any, Dict, List
from datetime import datetime
from infrafoundry.core.plugin_system import (
    ResourceResult,
    ValidationResult,
    ResourceSummary,
)
from infrafoundry_proxmox.resources.base import BaseResourceHandler
from infrafoundry_proxmox.exceptions import (
    ResourceNotFoundError,
    ProxmoxProviderError,
)


class VMResource(BaseResourceHandler):
    """Handles Proxmox VM resources."""

    def create(self, config: Dict[str, Any]) -> ResourceResult:
        """
        Create a Proxmox VM.

        Args:
            config: VM configuration
                Required: vmid, node
                Optional: name, cores, memory, disk, ...

        Returns:
            ResourceResult with created VM state
        """
        # Validate required fields
        validation = self.validate_config(config)
        if not validation.valid:
            raise ProxmoxProviderError(
                f"Invalid VM config: {validation.errors}"
            )

        vmid = config["vmid"]
        node = config["node"]

        # Create VM via API
        try:
            result = self.client.nodes(node).qemu.post(**config)
            task_id = result  # Proxmox returns task ID

            # Wait for task completion
            self.client.wait_for_task(task_id, node)

            # Read created VM state
            return self.read(str(vmid))

        except Exception as e:
            raise ProxmoxProviderError(
                f"Failed to create VM {vmid}: {e}"
            ) from e

    def read(self, resource_id: str) -> ResourceResult:
        """Read VM state."""
        vmid = int(resource_id)

        # Find which node the VM is on
        node = self._find_vm_node(vmid)
        if not node:
            raise ResourceNotFoundError(f"VM {vmid} not found")

        # Get VM config and status
        try:
            config = self.client.nodes(node).qemu(vmid).config.get()
            status = self.client.nodes(node).qemu(vmid).status.current.get()

            return ResourceResult(
                resource_id=str(vmid),
                resource_type="vm",
                state={
                    "vmid": vmid,
                    "node": node,
                    "name": config.get("name"),
                    "status": status.get("status"),
                    "cores": config.get("cores"),
                    "memory": config.get("memory"),
                    "config": config,
                    "runtime": status,
                },
                metadata={
                    "node": node,
                    "type": "qemu",
                },
                provider="proxmox",
                created_at=None,  # Proxmox doesn't track this
                updated_at=datetime.now(),
            )

        except Exception as e:
            raise ProxmoxProviderError(
                f"Failed to read VM {vmid}: {e}"
            ) from e

    def update(
        self,
        resource_id: str,
        config: Dict[str, Any]
    ) -> ResourceResult:
        """Update VM configuration."""
        vmid = int(resource_id)
        node = self._find_vm_node(vmid)

        if not node:
            raise ResourceNotFoundError(f"VM {vmid} not found")

        try:
            # Update VM config
            self.client.nodes(node).qemu(vmid).config.post(**config)

            # Return updated state
            return self.read(resource_id)

        except Exception as e:
            raise ProxmoxProviderError(
                f"Failed to update VM {vmid}: {e}"
            ) from e

    def delete(self, resource_id: str) -> None:
        """Delete VM."""
        vmid = int(resource_id)
        node = self._find_vm_node(vmid)

        if not node:
            raise ResourceNotFoundError(f"VM {vmid} not found")

        try:
            # Stop VM if running
            status = self.client.nodes(node).qemu(vmid).status.current.get()
            if status.get("status") == "running":
                self.client.nodes(node).qemu(vmid).status.stop.post()
                # Wait for stop
                self._wait_for_status(vmid, node, "stopped")

            # Delete VM
            task = self.client.nodes(node).qemu(vmid).delete()
            self.client.wait_for_task(task, node)

        except Exception as e:
            raise ProxmoxProviderError(
                f"Failed to delete VM {vmid}: {e}"
            ) from e

    def list(self) -> List[ResourceSummary]:
        """List all VMs."""
        vms = []

        try:
            # Get all nodes
            nodes = self.client.nodes.get()

            for node in nodes:
                node_name = node["node"]
                # Get VMs on this node
                node_vms = self.client.nodes(node_name).qemu.get()

                for vm in node_vms:
                    vms.append(
                        ResourceSummary(
                            resource_id=str(vm["vmid"]),
                            resource_type="vm",
                            name=vm.get("name"),
                            status=vm.get("status"),
                            metadata={"node": node_name},
                        )
                    )

            return vms

        except Exception as e:
            raise ProxmoxProviderError(
                f"Failed to list VMs: {e}"
            ) from e

    def validate_config(self, config: Dict[str, Any]) -> ValidationResult:
        """Validate VM configuration."""
        errors = []
        warnings = []

        # Required fields
        if "vmid" not in config:
            errors.append("vmid is required")
        elif not isinstance(config["vmid"], int):
            errors.append("vmid must be an integer")

        if "node" not in config:
            errors.append("node is required")

        # Optional but recommended
        if "name" not in config:
            warnings.append("VM name not specified")

        if "memory" in config and config["memory"] < 512:
            warnings.append("Memory < 512MB may be insufficient")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def _find_vm_node(self, vmid: int) -> str | None:
        """Find which node a VM is on."""
        try:
            nodes = self.client.nodes.get()
            for node in nodes:
                vms = self.client.nodes(node["node"]).qemu.get()
                for vm in vms:
                    if vm["vmid"] == vmid:
                        return node["node"]
            return None
        except Exception:
            return None

    def _wait_for_status(
        self,
        vmid: int,
        node: str,
        target_status: str,
        timeout: int = 60
    ) -> None:
        """Wait for VM to reach target status."""
        import time
        start = time.time()

        while time.time() - start < timeout:
            status = self.client.nodes(node).qemu(vmid).status.current.get()
            if status.get("status") == target_status:
                return
            time.sleep(2)

        raise ProxmoxProviderError(
            f"Timeout waiting for VM {vmid} to reach {target_status}"
        )
```

---

## CLI Integration

### CLI Registration Function

**File**: `src/infrafoundry_proxmox/cli.py`

```python
"""Proxmox provider CLI commands."""

import click
from infrafoundry.core.plugin_system import get_registry
from infrafoundry.core.config import load_provider_config


def register_cli(group: click.Group) -> None:
    """
    Register Proxmox CLI commands.

    Args:
        group: Click group for proxmox commands (foundry proxmox)
    """

    # VM commands
    vm_group = click.Group(name="vm", help="VM management")
    group.add_command(vm_group)

    @vm_group.command()
    @click.option("--vmid", required=True, type=int, help="VM ID")
    @click.option("--node", required=True, help="Proxmox node")
    @click.option("--name", help="VM name")
    @click.option("--cores", type=int, default=1, help="CPU cores")
    @click.option("--memory", type=int, default=1024, help="Memory (MB)")
    def create(vmid: int, node: str, name: str, cores: int, memory: int):
        """Create a new VM."""
        config = load_provider_config("proxmox")
        registry = get_registry()
        provider = registry.create_provider("proxmox", config)

        result = provider.create(
            "vm",
            {
                "vmid": vmid,
                "node": node,
                "name": name,
                "cores": cores,
                "memory": memory,
            }
        )

        click.echo(f"Created VM {result.resource_id}")

    @vm_group.command()
    @click.option("--vmid", required=True, type=int, help="VM ID")
    def status(vmid: int):
        """Get VM status."""
        config = load_provider_config("proxmox")
        registry = get_registry()
        provider = registry.create_provider("proxmox", config)

        result = provider.read("vm", str(vmid))
        state = result.state

        click.echo(f"VM {vmid}")
        click.echo(f"  Name: {state.get('name')}")
        click.echo(f"  Status: {state.get('status')}")
        click.echo(f"  Node: {state.get('node')}")
        click.echo(f"  Cores: {state.get('cores')}")
        click.echo(f"  Memory: {state.get('memory')} MB")

    @vm_group.command()
    def list():
        """List all VMs."""
        config = load_provider_config("proxmox")
        registry = get_registry()
        provider = registry.create_provider("proxmox", config)

        vms = provider.list_resources("vm")

        for vm in vms:
            click.echo(
                f"{vm.resource_id}: {vm.name} ({vm.status}) on {vm.metadata['node']}"
            )

    @vm_group.command()
    @click.option("--vmid", required=True, type=int, help="VM ID")
    @click.option("--action", type=click.Choice(["start", "stop", "restart"]))
    def control(vmid: int, action: str):
        """Control VM (start/stop/restart)."""
        # Implementation
        click.echo(f"VM {vmid}: {action}")

    # Container commands
    container_group = click.Group(name="container", help="Container management")
    group.add_command(container_group)

    @container_group.command()
    @click.option("--vmid", required=True, type=int, help="Container ID")
    def status(vmid: int):
        """Get container status."""
        # Similar to VM status
        pass

    # Snapshot commands
    @group.command()
    @click.option("--vmid", required=True, type=int, help="VM ID")
    @click.option("--name", required=True, help="Snapshot name")
    def snapshot(vmid: int, name: str):
        """Create a snapshot."""
        # Implementation
        click.echo(f"Creating snapshot {name} for VM {vmid}")

    # Storage commands
    @group.command()
    def storages():
        """List available storages."""
        # Implementation
        pass
```

### Resulting CLI Structure

```
foundry proxmox vm create --vmid 100 --node pve1 --name web-server
foundry proxmox vm status --vmid 100
foundry proxmox vm list
foundry proxmox vm control --vmid 100 --action start

foundry proxmox container status --vmid 200

foundry proxmox snapshot --vmid 100 --name pre-upgrade

foundry proxmox storages
```

---

## Configuration

### Configuration Model

**File**: `src/infrafoundry_proxmox/config.py`

```python
"""Proxmox provider configuration."""

from typing import Any, Dict
from dataclasses import dataclass


@dataclass
class ProxmoxConfig:
    """Proxmox provider configuration."""

    host: str                    # e.g., "https://proxmox.example.com:8006"
    user: str                    # e.g., "root@pam"
    token_name: str              # e.g., "api-token"
    token_value: str             # API token secret
    verify_ssl: bool = True      # Verify SSL certificates
    timeout: int = 30            # API timeout (seconds)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProxmoxConfig":
        """Create config from dictionary."""
        return cls(
            host=data["host"],
            user=data["user"],
            token_name=data["token_name"],
            token_value=data["token_value"],
            verify_ssl=data.get("verify_ssl", True),
            timeout=data.get("timeout", 30),
        )

    def validate(self) -> None:
        """Validate configuration."""
        if not self.host.startswith(("http://", "https://")):
            raise ValueError("host must start with http:// or https://")

        if not self.user:
            raise ValueError("user is required")

        if not self.token_name or not self.token_value:
            raise ValueError("token_name and token_value are required")
```

### Configuration File Format

```yaml
# infrafoundry.yaml
providers:
  proxmox:
    host: "https://proxmox.example.com:8006"
    user: "root@pam"
    token_name: "api-token"
    token_value: "xxx-secret-xxx"
    verify_ssl: false
    timeout: 60
```

### Environment Variable Support

```bash
INFRAFOUNDRY_PROXMOX_HOST=https://proxmox.example.com:8006
INFRAFOUNDRY_PROXMOX_USER=root@pam
INFRAFOUNDRY_PROXMOX_TOKEN_NAME=api-token
INFRAFOUNDRY_PROXMOX_TOKEN_VALUE=xxx-secret-xxx
INFRAFOUNDRY_PROXMOX_VERIFY_SSL=false
```

---

## Resource Types

### Supported Resource Types

| Resource Type | Description | Status |
|--------------|-------------|--------|
| `vm` | QEMU virtual machines | Primary |
| `container` | LXC containers | Primary |
| `snapshot` | VM/container snapshots | Secondary |
| `storage` | Storage management | Future |
| `network` | Network configuration | Future |
| `pool` | Resource pools | Future |

### VM Resource Schema

```python
{
    "vmid": int,              # Required, unique VM ID
    "node": str,              # Required, target node
    "name": str,              # Optional, VM name
    "cores": int,             # Optional, CPU cores (default: 1)
    "memory": int,            # Optional, Memory in MB (default: 1024)
    "disk": str,              # Optional, Disk config (e.g., "local:32")
    "network": str,           # Optional, Network config
    "iso": str,               # Optional, ISO image
    "ostype": str,            # Optional, OS type
    "description": str,       # Optional, description
}
```

### Container Resource Schema

```python
{
    "vmid": int,              # Required, unique container ID
    "node": str,              # Required, target node
    "hostname": str,          # Optional, container hostname
    "cores": int,             # Optional, CPU cores
    "memory": int,            # Optional, Memory in MB
    "rootfs": str,            # Optional, Root filesystem config
    "network": str,           # Optional, Network config
    "template": str,          # Optional, Container template
    "password": str,          # Optional, root password
}
```

---

## API Client Layer

### Proxmox Client Wrapper

**File**: `src/infrafoundry_proxmox/api/client.py`

```python
"""Proxmox API client wrapper."""

from proxmoxer import ProxmoxAPI
from typing import Any


class ProxmoxClient:
    """Wrapper around proxmoxer library."""

    def __init__(
        self,
        host: str,
        user: str,
        token_name: str,
        token_value: str,
        verify_ssl: bool = True,
    ):
        """
        Initialize Proxmox client.

        Args:
            host: Proxmox host URL
            user: Username (e.g., root@pam)
            token_name: API token name
            token_value: API token secret
            verify_ssl: Verify SSL certificates
        """
        self._api = ProxmoxAPI(
            host.replace("https://", "").replace("http://", ""),
            user=user,
            token_name=token_name,
            token_value=token_value,
            verify_ssl=verify_ssl,
        )

    def __getattr__(self, name: str) -> Any:
        """Proxy attribute access to underlying API."""
        return getattr(self._api, name)

    def version(self) -> dict:
        """Get Proxmox version."""
        return self._api.version.get()

    def wait_for_task(
        self,
        task_id: str,
        node: str,
        timeout: int = 300
    ) -> None:
        """
        Wait for a task to complete.

        Args:
            task_id: UPID task identifier
            node: Node running the task
            timeout: Max wait time in seconds

        Raises:
            TimeoutError: If task doesn't complete in time
            RuntimeError: If task fails
        """
        import time
        start = time.time()

        while time.time() - start < timeout:
            status = self._api.nodes(node).tasks(task_id).status.get()

            if status.get("status") == "stopped":
                exitstatus = status.get("exitstatus")
                if exitstatus == "OK":
                    return
                else:
                    raise RuntimeError(f"Task failed: {exitstatus}")

            time.sleep(2)

        raise TimeoutError(f"Task {task_id} did not complete in {timeout}s")
```

---

## Error Handling

### Exception Hierarchy

**File**: `src/infrafoundry_proxmox/exceptions.py`

```python
"""Proxmox provider exceptions."""

from infrafoundry.core.plugin_system import ProviderError


class ProxmoxProviderError(ProviderError):
    """Base exception for Proxmox provider."""


class ProxmoxAPIError(ProxmoxProviderError):
    """Proxmox API call failed."""


class ProxmoxAuthenticationError(ProxmoxProviderError):
    """Authentication to Proxmox failed."""


class ResourceNotFoundError(ProxmoxProviderError):
    """Proxmox resource not found."""


class ResourceConflictError(ProxmoxProviderError):
    """Resource already exists or conflicts."""


class TaskTimeoutError(ProxmoxProviderError):
    """Proxmox task timed out."""


class TaskFailedError(ProxmoxProviderError):
    """Proxmox task failed."""
```

### Error Handling Strategy

| Error Source | Exception | Handling |
|--------------|-----------|----------|
| API connection failure | `ProxmoxAPIError` | Retry with backoff |
| Authentication failure | `ProxmoxAuthenticationError` | Fail immediately, check config |
| Resource not found | `ResourceNotFoundError` | Return clear error |
| VMID conflict | `ResourceConflictError` | Suggest available VMIDs |
| Task timeout | `TaskTimeoutError` | Check task status manually |
| Invalid config | `ValidationError` | Show validation errors |

---

## Testing Strategy

### Test Categories

1. **Unit Tests**: Test individual components in isolation
2. **Integration Tests**: Test against real/mock Proxmox API
3. **CLI Tests**: Test CLI commands and output
4. **Contract Tests**: Verify provider implements protocol correctly

### Unit Tests

**File**: `tests/test_provider.py`

```python
"""Tests for Proxmox provider."""

import pytest
from unittest.mock import Mock, MagicMock
from infrafoundry_proxmox.provider import ProxmoxProvider
from infrafoundry_proxmox.exceptions import ProxmoxProviderError


@pytest.fixture
def mock_client():
    """Mock Proxmox client."""
    client = MagicMock()
    client.version.return_value = {"version": "7.4"}
    return client


@pytest.fixture
def provider(mock_client, monkeypatch):
    """Proxmox provider with mocked client."""
    config = {
        "host": "https://proxmox.test:8006",
        "user": "root@pam",
        "token_name": "test",
        "token_value": "secret",
    }

    # Patch client creation
    monkeypatch.setattr(
        "infrafoundry_proxmox.provider.ProxmoxClient",
        lambda **kwargs: mock_client
    )

    return ProxmoxProvider(config)


def test_provider_initialization(provider):
    """Test provider initializes correctly."""
    assert provider.config.host == "https://proxmox.test:8006"
    assert provider.config.user == "root@pam"


def test_create_vm(provider, mock_client):
    """Test VM creation."""
    # Setup mock
    mock_client.nodes.return_value.qemu.post.return_value = "UPID:task123"
    mock_client.wait_for_task.return_value = None
    mock_client.nodes.return_value.qemu.return_value.config.get.return_value = {
        "vmid": 100,
        "name": "test-vm",
    }

    # Create VM
    result = provider.create(
        "vm",
        {"vmid": 100, "node": "pve1", "name": "test-vm"}
    )

    assert result.resource_id == "100"
    assert result.resource_type == "vm"
    assert result.state["name"] == "test-vm"


def test_unsupported_resource_type(provider):
    """Test error on unsupported resource type."""
    with pytest.raises(ProxmoxProviderError, match="Unsupported resource type"):
        provider.create("invalid", {})
```

### Integration Tests

```python
"""Integration tests with real Proxmox API."""

import pytest
import os


@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("PROXMOX_HOST"),
    reason="PROXMOX_HOST not set"
)
def test_list_vms_real():
    """Test listing VMs against real Proxmox."""
    config = {
        "host": os.getenv("PROXMOX_HOST"),
        "user": os.getenv("PROXMOX_USER"),
        "token_name": os.getenv("PROXMOX_TOKEN_NAME"),
        "token_value": os.getenv("PROXMOX_TOKEN_VALUE"),
        "verify_ssl": False,
    }

    provider = ProxmoxProvider(config)
    vms = provider.list_resources("vm")

    assert isinstance(vms, list)
```

### CLI Tests

```python
"""CLI tests."""

from click.testing import CliRunner
from infrafoundry_proxmox.cli import register_cli
import click


def test_vm_list_command():
    """Test VM list command."""
    runner = CliRunner()
    group = click.Group()
    register_cli(group)

    result = runner.invoke(group, ["vm", "list"])

    assert result.exit_code == 0
```

### Contract Tests

```python
"""Verify provider implements required protocol."""

from infrafoundry.core.plugin_system import BaseProvider
from infrafoundry_proxmox.provider import ProxmoxProvider


def test_implements_base_provider():
    """Verify ProxmoxProvider implements BaseProvider protocol."""
    # Check all required methods exist
    assert hasattr(ProxmoxProvider, "create")
    assert hasattr(ProxmoxProvider, "read")
    assert hasattr(ProxmoxProvider, "update")
    assert hasattr(ProxmoxProvider, "delete")
    assert hasattr(ProxmoxProvider, "list_resources")
    assert hasattr(ProxmoxProvider, "validate_config")
```

---

## Migration Plan

### What Gets Moved

| Current Location | New Location | Notes |
|-----------------|--------------|-------|
| `src/infrafoundry/providers/proxmox/` | `packages/infrafoundry-proxmox/src/infrafoundry_proxmox/` | Provider code |
| `src/infrafoundry/cli/commands/proxmox_*.py` | `packages/infrafoundry-proxmox/src/infrafoundry_proxmox/cli.py` | CLI commands |
| Proxmox tests | `packages/infrafoundry-proxmox/tests/` | Tests |
| Proxmox docs | `packages/infrafoundry-proxmox/docs/` | Documentation |

### Files to Create

1. `packages/infrafoundry-proxmox/pyproject.toml` - Package metadata
2. `packages/infrafoundry-proxmox/README.md` - Package README
3. `packages/infrafoundry-proxmox/src/infrafoundry_proxmox/__init__.py` - Registration
4. `packages/infrafoundry-proxmox/src/infrafoundry_proxmox/provider.py` - Provider class
5. `packages/infrafoundry-proxmox/src/infrafoundry_proxmox/cli.py` - CLI registration

### Files to Modify in Core

1. Remove: `src/infrafoundry/providers/proxmox/`
2. Remove: `src/infrafoundry/cli/commands/proxmox_*.py`
3. Add: Plugin discovery system
4. Add: Provider registry
5. Update: CLI initialization to use plugin system
6. Update: `pyproject.toml` to include `infrafoundry-proxmox` as bundled dependency

### Migration Steps

1. **Create package structure** in `packages/infrafoundry-proxmox/`
2. **Copy existing code** to new locations
3. **Refactor to match plugin contract**:
   - Create `register()` function
   - Ensure `ProxmoxProvider` implements `BaseProvider`
   - Create CLI registration function
4. **Add entry point** to `pyproject.toml`
5. **Update imports** in copied code
6. **Move tests** and update imports
7. **Test in isolation**: `uv pip install -e packages/infrafoundry-proxmox`
8. **Update core** to use plugin system
9. **Bundle in meta-package**: Add as dependency to main `infrafoundry` package
10. **Verify everything works**

### Backward Compatibility

Not required based on user input - breaking changes acceptable.

---

## Dependencies

### Package Dependencies

**File**: `packages/infrafoundry-proxmox/pyproject.toml`

```toml
[project]
name = "infrafoundry-proxmox"
version = "0.1.0"
description = "Proxmox provider plugin for InfraFoundry"
requires-python = ">=3.11"

dependencies = [
    "infrafoundry-core>=0.1.0,<1.0.0",  # Core plugin system
    "proxmoxer>=2.0.0",                  # Proxmox API client
    "requests>=2.31.0",                  # HTTP client
    "click>=8.0",                        # CLI (might come from core)
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
    "pytest-mock>=3.11",
    "mypy>=1.5",
    "ruff>=0.1.0",
]

[project.entry-points."infrafoundry.providers"]
proxmox = "infrafoundry_proxmox:register"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = "test_*.py"
python_functions = "test_*"

[tool.mypy]
strict = true
warn_return_any = true
warn_unused_configs = true

[tool.ruff]
line-length = 88
target-version = "py311"
```

### Dependency Considerations

1. **proxmoxer**: Only in this package, not in core
2. **click**: Might be redundant if core provides it
3. **infrafoundry-core**: Required for plugin interfaces
4. **Version pinning**: Use flexible ranges for forward compatibility

---

## Success Criteria

- [ ] Package structure created
- [ ] `register()` function implemented
- [ ] `ProxmoxProvider` implements `BaseProvider` protocol
- [ ] Entry point declared in `pyproject.toml`
- [ ] CLI registration function implemented
- [ ] All resource types work (vm, container, snapshot)
- [ ] Tests passing (unit + integration)
- [ ] Package installable: `uv pip install -e packages/infrafoundry-proxmox`
- [ ] Provider discoverable by core
- [ ] CLI commands work: `foundry proxmox vm list`
- [ ] Can create/read/update/delete resources
- [ ] Documentation complete
- [ ] No Proxmox code remains in core

---

## Open Questions

1. **Shared utilities**: Should common provider utilities go in a `infrafoundry-provider-sdk` package?
2. **CLI helpers**: Should core provide CLI helper functions for consistent output?
3. **Task polling**: Should task waiting be generic or provider-specific?
4. **Error formatting**: Should errors follow a standard format?
5. **Logging**: Should providers use core's logger or their own?
6. **Config validation**: Should core validate provider configs or trust providers?

---

## Next Steps

1. Review and approve this design
2. Create the package structure
3. Implement core plugin system first
4. Then extract Proxmox provider
5. Test integration
6. Iterate and refine
