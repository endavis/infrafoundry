# Secret Backend Plugin Type Design

**Version:** 1.0
**Date:** 2025-12-28
**Status:** Design Phase
**Related:** [Plugin System Design](./PLUGIN_SYSTEM_DESIGN.md)

## Table of Contents

1. [Overview](#overview)
2. [Why Secrets as Plugin Type](#why-secrets-as-plugin-type)
3. [Secret Backend Protocol](#secret-backend-protocol)
4. [Plugin Type Implementation](#plugin-type-implementation)
5. [Built-in Backends](#built-in-backends)
6. [Configuration](#configuration)
7. [Secret Resolution](#secret-resolution)
8. [Provider Integration](#provider-integration)
9. [Security Considerations](#security-considerations)
10. [Third-Party Backends](#third-party-backends)
11. [Testing Strategy](#testing-strategy)
12. [Migration Path](#migration-path)

---

## Overview

### Purpose

The secret backend plugin type provides a **pluggable secret management system** for InfraFoundry, allowing different secret storage backends to be used in different environments without changing provider configurations.

### Goals

1. **Separation of Concerns**: Providers don't manage secrets directly
2. **Environment Flexibility**: Dev uses env vars, prod uses Vault (same config)
3. **Security**: Centralized secret access with audit logging
4. **Extensibility**: Easy to add new backends (AWS Secrets Manager, Azure Key Vault, etc.)
5. **Simple Default**: Works out of the box with environment variables

### Use Cases

**Development:**
```bash
export PROXMOX_TOKEN="dev-token-123"
foundry proxmox vm list
```

**Production:**
```yaml
secrets:
  backend: vault
  config:
    url: "https://vault.prod.example.com"
    auth_method: "kubernetes"
```

**Multi-Environment:**
```yaml
# Different backends per environment
secrets:
  backend: "${INFRAFOUNDRY_SECRET_BACKEND:-env}"  # env in dev, vault in prod
```

---

## Why Secrets as Plugin Type

### Problems with Inline Secrets

**Hardcoded secrets in config:**
```yaml
providers:
  proxmox:
    token_value: "super-secret-token-123"  # ❌ Committed to git
```

**Issues:**
- Secrets in version control
- No rotation without config changes
- Different secrets per environment = different config files
- No audit trail of secret access
- Can't use enterprise secret management

### Solution: Secret Backend Abstraction

**Reference secrets by key:**
```yaml
providers:
  proxmox:
    token_value: "secret://proxmox/token"  # ✅ Resolved at runtime
```

**Benefits:**
- Secrets never in config files
- Same config across environments
- Centralized secret management
- Secret rotation without redeployment
- Audit logging of access
- Enterprise secret backend integration

---

## Secret Backend Protocol

### Base Protocol

Every secret backend implements this protocol:

**File**: `src/infrafoundry/secrets/protocol.py`

```python
"""Secret backend protocol."""

from typing import Protocol, Optional, Dict, Any, List
from abc import abstractmethod


class SecretBackend(Protocol):
    """
    Protocol that all secret backends must implement.

    Secret backends provide secure storage and retrieval of sensitive
    configuration values like API tokens, passwords, and certificates.
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        """
        Initialize secret backend with configuration.

        Args:
            config: Backend-specific configuration
        """

    @abstractmethod
    def get_secret(self, key: str) -> str:
        """
        Retrieve a secret value by key.

        Args:
            key: Secret key/path (e.g., "proxmox/token", "aws/access_key")

        Returns:
            Secret value as string

        Raises:
            SecretNotFoundError: If secret doesn't exist
            SecretBackendError: If retrieval fails
        """

    @abstractmethod
    def list_secrets(self, prefix: str = "") -> List[str]:
        """
        List available secret keys.

        Args:
            prefix: Optional prefix to filter secrets (e.g., "proxmox/")

        Returns:
            List of secret keys

        Raises:
            SecretBackendError: If listing fails
        """

    def set_secret(self, key: str, value: str) -> None:
        """
        Store a secret value (optional).

        Not all backends support writing secrets. Read-only backends
        should raise NotImplementedError.

        Args:
            key: Secret key/path
            value: Secret value to store

        Raises:
            NotImplementedError: If backend is read-only
            SecretBackendError: If storage fails
        """
        raise NotImplementedError("This backend does not support writing secrets")

    def delete_secret(self, key: str) -> None:
        """
        Delete a secret (optional).

        Not all backends support deleting secrets. Read-only backends
        should raise NotImplementedError.

        Args:
            key: Secret key/path to delete

        Raises:
            NotImplementedError: If backend is read-only
            SecretNotFoundError: If secret doesn't exist
            SecretBackendError: If deletion fails
        """
        raise NotImplementedError("This backend does not support deleting secrets")

    def health_check(self) -> bool:
        """
        Check if backend is accessible.

        Returns:
            True if backend is healthy, False otherwise
        """
        try:
            # Default implementation: try listing secrets
            self.list_secrets()
            return True
        except Exception:
            return False

    def close(self) -> None:
        """
        Clean up resources (connections, sessions, etc.).

        Called when backend is no longer needed.
        """
        pass
```

### Secret Metadata (Optional Enhancement)

Some backends might provide metadata about secrets:

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class SecretMetadata:
    """Metadata about a secret."""

    key: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    version: Optional[str] = None
    tags: Dict[str, str] = field(default_factory=dict)


class SecretBackendWithMetadata(SecretBackend):
    """Extended protocol for backends that support metadata."""

    def get_secret_metadata(self, key: str) -> SecretMetadata:
        """Get metadata about a secret."""
```

---

## Plugin Type Implementation

### Secret Backend Plugin Type

**File**: `src/infrafoundry/secrets/plugin_type.py`

```python
"""Secret backend plugin type implementation."""

from typing import Any, List
import logging

from infrafoundry.core.plugin_system.plugin_type import (
    PluginType,
    PluginMetadata,
    ValidationResult,
)
from infrafoundry.secrets.protocol import SecretBackend


logger = logging.getLogger(__name__)


class SecretBackendPluginType(PluginType):
    """Secret backend plugin type."""

    @property
    def entry_point_group(self) -> str:
        return "infrafoundry.secrets"

    @property
    def type_name(self) -> str:
        return "secret_backend"

    def load_plugin(self, entry_point) -> PluginMetadata:
        """Load a secret backend plugin."""
        # Load the registration function
        register_func = entry_point.load()

        # Call it to get backend metadata
        backend_metadata = register_func()

        # Convert to generic PluginMetadata
        return PluginMetadata(
            name=backend_metadata.name,
            version=backend_metadata.version,
            plugin_type="secret_backend",
            description=backend_metadata.description,
            implementation=backend_metadata.backend_class,
            metadata={
                "read_only": backend_metadata.read_only,
                "requires_config": backend_metadata.requires_config,
                "author": backend_metadata.author,
                "url": backend_metadata.url,
            }
        )

    def validate_plugin(self, metadata: PluginMetadata) -> ValidationResult:
        """Validate secret backend implements required protocol."""
        errors = []
        warnings = []

        backend_class = metadata.implementation

        # Check required methods
        required_methods = ["get_secret", "list_secrets"]

        for method in required_methods:
            if not hasattr(backend_class, method):
                errors.append(f"Missing required method: {method}")

        # Check optional methods
        if not hasattr(backend_class, "set_secret"):
            warnings.append("Backend does not support writing secrets (read-only)")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def register_cli(self, app: Any, plugins: List[PluginMetadata]) -> None:
        """Register secret backend CLI commands."""
        import click

        # Create secrets management group
        secrets_group = click.Group(
            name="secrets",
            help="Secret management commands"
        )
        app.add_command(secrets_group)

        @secrets_group.command()
        def backends():
            """List available secret backends."""
            click.echo("Available secret backends:")
            for plugin in plugins:
                read_only = plugin.metadata.get("read_only", False)
                access = "read-only" if read_only else "read-write"
                click.echo(f"  {plugin.name}: {plugin.description} ({access})")

        @secrets_group.command()
        @click.argument("key")
        def get(key: str):
            """Get a secret value."""
            from infrafoundry.secrets import get_secret_backend
            backend = get_secret_backend()
            try:
                value = backend.get_secret(key)
                click.echo(value)
            except Exception as e:
                click.echo(f"Error: {e}", err=True)
                raise click.Abort()

        @secrets_group.command()
        @click.option("--prefix", default="", help="Filter by prefix")
        def list(prefix: str):
            """List available secrets."""
            from infrafoundry.secrets import get_secret_backend
            backend = get_secret_backend()
            try:
                secrets = backend.list_secrets(prefix)
                for secret_key in secrets:
                    click.echo(secret_key)
            except Exception as e:
                click.echo(f"Error: {e}", err=True)
                raise click.Abort()

        @secrets_group.command()
        @click.argument("key")
        @click.argument("value")
        def set(key: str, value: str):
            """Set a secret value."""
            from infrafoundry.secrets import get_secret_backend
            backend = get_secret_backend()
            try:
                backend.set_secret(key, value)
                click.echo(f"Secret '{key}' set successfully")
            except NotImplementedError:
                click.echo("Error: This backend does not support writing secrets", err=True)
                raise click.Abort()
            except Exception as e:
                click.echo(f"Error: {e}", err=True)
                raise click.Abort()
```

### Secret Backend Metadata

```python
from dataclasses import dataclass
from typing import Type, Optional


@dataclass
class SecretBackendMetadata:
    """Metadata about a secret backend plugin."""

    name: str                           # e.g., "vault", "aws", "env"
    version: str                        # e.g., "0.1.0"
    backend_class: Type[SecretBackend]  # Implementation class
    description: str                    # Human-readable description
    read_only: bool = False            # True if backend can't write secrets
    requires_config: bool = False      # True if backend needs configuration
    author: Optional[str] = None
    url: Optional[str] = None
```

---

## Built-in Backends

InfraFoundry ships with two built-in secret backends:

### 1. Environment Variable Backend

**File**: `src/infrafoundry/secrets/env_backend.py`

```python
"""Environment variable secret backend."""

import os
from typing import Dict, Any, List

from infrafoundry.secrets.protocol import SecretBackend
from infrafoundry.secrets.exceptions import (
    SecretNotFoundError,
    SecretBackendError,
)


class EnvSecretBackend(SecretBackend):
    """
    Secret backend that reads from environment variables.

    Secret keys are converted to environment variable names:
    - "proxmox/token" -> PROXMOX_TOKEN
    - "aws/access_key" -> AWS_ACCESS_KEY

    This is the default backend and requires no configuration.
    """

    def __init__(self, config: Dict[str, Any] = None):
        """Initialize environment backend."""
        self.config = config or {}
        self.prefix = self.config.get("prefix", "")

    def get_secret(self, key: str) -> str:
        """Get secret from environment variable."""
        env_var = self._key_to_env_var(key)

        value = os.getenv(env_var)
        if value is None:
            raise SecretNotFoundError(
                f"Secret '{key}' not found (expected env var: {env_var})"
            )

        return value

    def list_secrets(self, prefix: str = "") -> List[str]:
        """
        List secrets from environment.

        Note: This lists all environment variables that look like secrets.
        It's not perfect but useful for debugging.
        """
        secrets = []

        for env_var in os.environ:
            # Skip system variables
            if env_var.startswith(("PATH", "HOME", "USER", "SHELL")):
                continue

            # Convert env var back to secret key format
            key = self._env_var_to_key(env_var)

            if not prefix or key.startswith(prefix):
                secrets.append(key)

        return sorted(secrets)

    def _key_to_env_var(self, key: str) -> str:
        """
        Convert secret key to environment variable name.

        Examples:
            proxmox/token -> PROXMOX_TOKEN
            aws/access_key -> AWS_ACCESS_KEY
        """
        # Remove any leading/trailing slashes
        key = key.strip("/")

        # Replace slashes with underscores, convert to uppercase
        env_var = key.replace("/", "_").replace("-", "_").upper()

        # Add prefix if configured
        if self.prefix:
            env_var = f"{self.prefix}_{env_var}"

        return env_var

    def _env_var_to_key(self, env_var: str) -> str:
        """
        Convert environment variable name to secret key.

        Examples:
            PROXMOX_TOKEN -> proxmox/token
            AWS_ACCESS_KEY -> aws/access_key
        """
        # Remove prefix if configured
        if self.prefix and env_var.startswith(f"{self.prefix}_"):
            env_var = env_var[len(self.prefix) + 1:]

        # Convert to lowercase, replace underscores with slashes
        key = env_var.lower().replace("_", "/")

        return key


def register() -> SecretBackendMetadata:
    """Register environment variable backend."""
    return SecretBackendMetadata(
        name="env",
        version="0.1.0",
        backend_class=EnvSecretBackend,
        description="Read secrets from environment variables",
        read_only=True,
        requires_config=False,
        author="InfraFoundry Team",
    )
```

### 2. File Backend

**File**: `src/infrafoundry/secrets/file_backend.py`

```python
"""File-based secret backend."""

import json
from pathlib import Path
from typing import Dict, Any, List

from infrafoundry.secrets.protocol import SecretBackend
from infrafoundry.secrets.exceptions import (
    SecretNotFoundError,
    SecretBackendError,
)


class FileSecretBackend(SecretBackend):
    """
    Secret backend that reads from JSON file.

    Secrets stored in JSON format:
    {
        "proxmox/token": "secret-value",
        "aws/access_key": "AKIAIOSFODNN7EXAMPLE"
    }

    Supports both reading and writing secrets.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize file backend.

        Args:
            config: Must contain "path" key with file path
        """
        if "path" not in config:
            raise SecretBackendError("File backend requires 'path' in config")

        self.path = Path(config["path"]).expanduser()
        self.secrets: Dict[str, str] = {}

        # Load secrets from file
        self._load_secrets()

    def _load_secrets(self) -> None:
        """Load secrets from file."""
        if not self.path.exists():
            # Create empty file
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text("{}")
            self.secrets = {}
            return

        try:
            with open(self.path) as f:
                self.secrets = json.load(f)
        except json.JSONDecodeError as e:
            raise SecretBackendError(f"Invalid JSON in secrets file: {e}")
        except Exception as e:
            raise SecretBackendError(f"Failed to load secrets file: {e}")

    def _save_secrets(self) -> None:
        """Save secrets to file."""
        try:
            with open(self.path, "w") as f:
                json.dump(self.secrets, f, indent=2)
        except Exception as e:
            raise SecretBackendError(f"Failed to save secrets file: {e}")

    def get_secret(self, key: str) -> str:
        """Get secret from file."""
        if key not in self.secrets:
            raise SecretNotFoundError(f"Secret '{key}' not found in {self.path}")
        return self.secrets[key]

    def list_secrets(self, prefix: str = "") -> List[str]:
        """List secrets from file."""
        if not prefix:
            return sorted(self.secrets.keys())

        return sorted(
            key for key in self.secrets.keys()
            if key.startswith(prefix)
        )

    def set_secret(self, key: str, value: str) -> None:
        """Set secret in file."""
        self.secrets[key] = value
        self._save_secrets()

    def delete_secret(self, key: str) -> None:
        """Delete secret from file."""
        if key not in self.secrets:
            raise SecretNotFoundError(f"Secret '{key}' not found")

        del self.secrets[key]
        self._save_secrets()


def register() -> SecretBackendMetadata:
    """Register file backend."""
    return SecretBackendMetadata(
        name="file",
        version="0.1.0",
        backend_class=FileSecretBackend,
        description="Read/write secrets from JSON file",
        read_only=False,
        requires_config=True,
        author="InfraFoundry Team",
    )
```

### Entry Point Declaration

**File**: `infrafoundry-core/pyproject.toml`

```toml
[project.entry-points."infrafoundry.secrets"]
env = "infrafoundry.secrets.env_backend:register"
file = "infrafoundry.secrets.file_backend:register"
```

---

## Configuration

### Global Configuration

**File**: `infrafoundry.yaml`

```yaml
# Secret backend configuration
secrets:
  backend: env  # or file, vault, aws, etc.
  config:
    # Backend-specific configuration
    # For env backend: no config needed
    # For file backend:
    path: "~/.infrafoundry/secrets.json"
```

### Environment Variable Override

```bash
# Override which backend to use
export INFRAFOUNDRY_SECRET_BACKEND=vault

# Backend-specific config via env vars
export INFRAFOUNDRY_SECRET_VAULT_URL=https://vault.example.com
export INFRAFOUNDRY_SECRET_VAULT_TOKEN=hvs.xxxxx
```

### Backend Selection Logic

```python
def get_configured_backend() -> str:
    """Determine which backend to use."""

    # 1. Environment variable takes precedence
    if backend := os.getenv("INFRAFOUNDRY_SECRET_BACKEND"):
        return backend

    # 2. Check config file
    config = load_config()
    if "secrets" in config and "backend" in config["secrets"]:
        return config["secrets"]["backend"]

    # 3. Default to env backend
    return "env"
```

---

## Secret Resolution

### Secret Reference Format

Secrets are referenced using the `secret://` URI scheme:

```yaml
providers:
  proxmox:
    token_value: "secret://proxmox/token"

  aws:
    access_key: "secret://aws/access_key"
    secret_key: "secret://aws/secret_key"
```

### Resolution Process

```python
def resolve_secrets(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively resolve secret references in configuration.

    Args:
        config: Configuration dict that may contain secret:// references

    Returns:
        Configuration with secrets resolved
    """
    backend = get_secret_backend()

    def resolve_value(value):
        if isinstance(value, str) and value.startswith("secret://"):
            secret_key = value.removeprefix("secret://")
            return backend.get_secret(secret_key)
        elif isinstance(value, dict):
            return {k: resolve_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [resolve_value(item) for item in value]
        else:
            return value

    return resolve_value(config)
```

### When Resolution Happens

Secrets are resolved **lazily** when providers are instantiated:

```python
class ProviderRegistry:
    def create_provider(self, name: str, config: Dict[str, Any]):
        """Create provider instance with secrets resolved."""

        # Resolve secret references
        resolved_config = resolve_secrets(config)

        # Create provider with resolved config
        provider_class = self.get_provider_class(name)
        return provider_class(resolved_config)
```

---

## Provider Integration

### Provider Configuration with Secrets

Providers receive **resolved** configuration (secrets already fetched):

```python
class ProxmoxProvider:
    def __init__(self, config: Dict[str, Any]):
        # Config has secrets already resolved
        # token_value is actual token, not "secret://..." reference

        self.config = ProxmoxConfig.from_dict(config)
        # self.config.token_value = "actual-token-value"
```

### Pydantic SecretStr Integration

Pydantic's `SecretStr` prevents secrets from being logged:

```python
from pydantic import BaseModel, SecretStr


class ProxmoxConfig(BaseModel):
    host: str
    user: str
    token_name: str
    token_value: SecretStr  # Never logged or printed

    class Config:
        # Prevent accidental logging
        json_encoders = {
            SecretStr: lambda v: "***REDACTED***"
        }
```

Usage:
```python
config = ProxmoxConfig(
    host="https://proxmox.example.com:8006",
    user="root@pam",
    token_name="api-token",
    token_value="actual-secret-token",  # Resolved from backend
)

# Logging config won't show the token
logger.info(f"Proxmox config: {config}")
# Output: token_value=SecretStr('***REDACTED***')

# Access actual value when needed
token = config.token_value.get_secret_value()
```

---

## Security Considerations

### 1. Secret Storage

**Environment Backend:**
- ✅ No secrets in files
- ✅ Process isolation
- ⚠️ Visible in process list
- ⚠️ Inherited by child processes

**File Backend:**
- ⚠️ Secrets in plaintext file
- ⚠️ File permissions critical (chmod 600)
- ✅ Easy to backup/restore
- ⚠️ Should encrypt in production

**Vault/Cloud Backends:**
- ✅ Secrets encrypted at rest
- ✅ Access control and audit logging
- ✅ Secret rotation
- ✅ Enterprise security

### 2. Secret Transmission

Secrets are resolved at runtime and **never**:
- Written to logs (Pydantic SecretStr)
- Stored in state files (state has resource IDs, not credentials)
- Sent over network (except to backend API)
- Cached in memory longer than necessary

### 3. Access Control

```python
# Only authorized backends can access secrets
backend = get_secret_backend()  # Based on config

# Audit logging
logger.info(f"Secret accessed: {key} by {provider}")
```

### 4. Secret Rotation

With secret backends, rotation is simple:

**Environment Backend:**
```bash
# Update env var
export PROXMOX_TOKEN="new-token-456"

# Restart infrafoundry (picks up new value)
foundry proxmox vm list
```

**Vault Backend:**
```bash
# Rotate in Vault
vault kv put secret/proxmox/token value="new-token-456"

# Infrafoundry automatically gets new value (no restart needed)
foundry proxmox vm list
```

### 5. Encrypted File Backend (Future)

```python
class EncryptedFileBackend(FileSecretBackend):
    """File backend with encryption."""

    def __init__(self, config):
        self.encryption_key = self._load_key(config["key_path"])
        super().__init__(config)

    def _load_secrets(self):
        encrypted_data = self.path.read_bytes()
        decrypted_data = decrypt(encrypted_data, self.encryption_key)
        self.secrets = json.loads(decrypted_data)

    def _save_secrets(self):
        data = json.dumps(self.secrets)
        encrypted_data = encrypt(data, self.encryption_key)
        self.path.write_bytes(encrypted_data)
```

---

## Third-Party Backends

### HashiCorp Vault Backend

**Package**: `infrafoundry-vault-secrets`

**File**: `src/infrafoundry_vault_secrets/backend.py`

```python
"""HashiCorp Vault secret backend."""

import hvac
from typing import Dict, Any, List

from infrafoundry.secrets.protocol import SecretBackend


class VaultBackend(SecretBackend):
    """HashiCorp Vault secret backend."""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Vault backend.

        Config:
            url: Vault server URL
            token: Vault token (or use auth_method)
            auth_method: Authentication method (token, kubernetes, etc.)
            mount_point: KV mount point (default: "secret")
        """
        self.url = config["url"]
        self.mount_point = config.get("mount_point", "secret")

        # Initialize Vault client
        self.client = hvac.Client(url=self.url)

        # Authenticate
        if "token" in config:
            self.client.token = config["token"]
        elif config.get("auth_method") == "kubernetes":
            self._auth_kubernetes(config)
        else:
            raise ValueError("Must provide token or auth_method")

        # Verify authentication
        if not self.client.is_authenticated():
            raise ValueError("Failed to authenticate with Vault")

    def get_secret(self, key: str) -> str:
        """Get secret from Vault."""
        try:
            # Read from KV v2
            response = self.client.secrets.kv.v2.read_secret_version(
                path=key,
                mount_point=self.mount_point,
            )

            # Extract value (assumes secret has "value" key)
            data = response["data"]["data"]
            return data["value"]

        except hvac.exceptions.InvalidPath:
            raise SecretNotFoundError(f"Secret '{key}' not found in Vault")
        except Exception as e:
            raise SecretBackendError(f"Failed to get secret from Vault: {e}")

    def list_secrets(self, prefix: str = "") -> List[str]:
        """List secrets from Vault."""
        try:
            response = self.client.secrets.kv.v2.list_secrets(
                path=prefix,
                mount_point=self.mount_point,
            )
            return response["data"]["keys"]
        except Exception as e:
            raise SecretBackendError(f"Failed to list secrets: {e}")

    def set_secret(self, key: str, value: str) -> None:
        """Set secret in Vault."""
        try:
            self.client.secrets.kv.v2.create_or_update_secret(
                path=key,
                secret={"value": value},
                mount_point=self.mount_point,
            )
        except Exception as e:
            raise SecretBackendError(f"Failed to set secret: {e}")


def register():
    """Register Vault backend."""
    return SecretBackendMetadata(
        name="vault",
        version="0.1.0",
        backend_class=VaultBackend,
        description="HashiCorp Vault secret backend",
        read_only=False,
        requires_config=True,
        author="InfraFoundry Community",
        url="https://github.com/infrafoundry/infrafoundry-vault-secrets",
    )
```

**Entry Point:**
```toml
# infrafoundry-vault-secrets/pyproject.toml
[project]
name = "infrafoundry-vault-secrets"
dependencies = [
    "infrafoundry-core>=0.1.0",
    "hvac>=1.0.0",  # Vault client library
]

[project.entry-points."infrafoundry.secrets"]
vault = "infrafoundry_vault_secrets:register"
```

**Usage:**
```yaml
# infrafoundry.yaml
secrets:
  backend: vault
  config:
    url: "https://vault.prod.example.com:8200"
    token: "${VAULT_TOKEN}"
    mount_point: "infra-secrets"
```

### AWS Secrets Manager Backend

**Package**: `infrafoundry-aws-secrets`

```python
"""AWS Secrets Manager backend."""

import boto3
from typing import Dict, Any, List


class AWSSecretsBackend(SecretBackend):
    """AWS Secrets Manager backend."""

    def __init__(self, config: Dict[str, Any]):
        self.region = config.get("region", "us-east-1")
        self.client = boto3.client("secretsmanager", region_name=self.region)

    def get_secret(self, key: str) -> str:
        """Get secret from AWS Secrets Manager."""
        try:
            response = self.client.get_secret_value(SecretId=key)
            return response["SecretString"]
        except self.client.exceptions.ResourceNotFoundException:
            raise SecretNotFoundError(f"Secret '{key}' not found in AWS")
        except Exception as e:
            raise SecretBackendError(f"Failed to get secret: {e}")

    def list_secrets(self, prefix: str = "") -> List[str]:
        """List secrets from AWS Secrets Manager."""
        secrets = []
        paginator = self.client.get_paginator("list_secrets")

        for page in paginator.paginate():
            for secret in page["SecretList"]:
                name = secret["Name"]
                if not prefix or name.startswith(prefix):
                    secrets.append(name)

        return secrets
```

---

## Testing Strategy

### Unit Tests

**Test Environment Backend:**
```python
def test_env_backend_get_secret(monkeypatch):
    """Test getting secret from environment."""
    monkeypatch.setenv("PROXMOX_TOKEN", "test-token-123")

    backend = EnvSecretBackend()
    value = backend.get_secret("proxmox/token")

    assert value == "test-token-123"


def test_env_backend_secret_not_found():
    """Test error when secret not found."""
    backend = EnvSecretBackend()

    with pytest.raises(SecretNotFoundError):
        backend.get_secret("nonexistent/secret")
```

**Test File Backend:**
```python
def test_file_backend_read_write(tmp_path):
    """Test file backend read/write."""
    secrets_file = tmp_path / "secrets.json"

    backend = FileSecretBackend({"path": str(secrets_file)})

    # Write secret
    backend.set_secret("test/key", "test-value")

    # Read secret
    value = backend.get_secret("test/key")
    assert value == "test-value"
```

### Integration Tests

**Test Secret Resolution:**
```python
def test_secret_resolution(monkeypatch):
    """Test secret resolution in config."""
    monkeypatch.setenv("PROXMOX_TOKEN", "resolved-token")

    config = {
        "host": "https://proxmox.example.com",
        "token": "secret://proxmox/token",
    }

    resolved = resolve_secrets(config)

    assert resolved["token"] == "resolved-token"
```

### Mock Backends for Testing

```python
class MockSecretBackend(SecretBackend):
    """Mock backend for testing."""

    def __init__(self, config=None):
        self.secrets = {
            "proxmox/token": "mock-token-123",
            "aws/access_key": "mock-access-key",
        }

    def get_secret(self, key: str) -> str:
        if key not in self.secrets:
            raise SecretNotFoundError(key)
        return self.secrets[key]

    def list_secrets(self, prefix: str = "") -> List[str]:
        return [k for k in self.secrets if k.startswith(prefix)]
```

---

## Migration Path

### Phase 1: Build Infrastructure
- [ ] Define `SecretBackend` protocol
- [ ] Implement `SecretBackendPluginType`
- [ ] Build secret resolution system
- [ ] Write tests for resolution

### Phase 2: Built-in Backends
- [ ] Implement `EnvSecretBackend`
- [ ] Implement `FileSecretBackend`
- [ ] Register as entry points
- [ ] Integration tests

### Phase 3: Provider Integration
- [ ] Update provider instantiation to resolve secrets
- [ ] Update Proxmox provider config to use SecretStr
- [ ] Test with both env and file backends
- [ ] Documentation

### Phase 4: Third-Party Backends (Community)
- [ ] Vault backend (separate package)
- [ ] AWS Secrets Manager backend
- [ ] Azure Key Vault backend
- [ ] Documentation for writing backends

---

## Success Criteria

- [ ] `SecretBackend` protocol defined
- [ ] Plugin type registered and discoverable
- [ ] `EnvSecretBackend` works with env vars
- [ ] `FileSecretBackend` reads/writes JSON file
- [ ] Secret resolution works: `secret://path` → actual value
- [ ] Providers instantiate with resolved secrets
- [ ] Pydantic `SecretStr` prevents logging secrets
- [ ] CLI commands: `foundry secrets list/get/set`
- [ ] Tests passing for all backends
- [ ] Documentation complete
- [ ] Example third-party backend (Vault)

---

## Open Questions

1. **Secret Caching**: Should backends cache secrets in memory? For how long?
2. **Secret Versions**: Should we support versioned secrets (get specific version)?
3. **Secret Metadata**: Should backends expose creation/update timestamps?
4. **Batch Operations**: Should we support `get_secrets([key1, key2])` for efficiency?
5. **Secret Validation**: Should backends validate secret format (e.g., is it a valid token)?
6. **Encryption at Rest**: Should file backend support encryption by default?
7. **Audit Logging**: Where do we log secret access? Core or backend?

---

## Conclusion

Secret backends as a plugin type provide:

- **Security**: Centralized secret management with audit logging
- **Flexibility**: Different backends for different environments
- **Extensibility**: Easy to add enterprise secret systems
- **Simplicity**: Works out of the box with environment variables
- **Standards**: Follows security best practices

This architecture allows InfraFoundry to handle secrets securely from day one, with a clear path to enterprise secret management systems.
