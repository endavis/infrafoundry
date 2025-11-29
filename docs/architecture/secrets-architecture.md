# Secrets Management Architecture

**Version:** 1.0
**Last Updated:** 2025-11-29

## Overview

InfraFoundry's secrets management system uses a **pluggable provider architecture** that allows you to integrate with any secret storage backend. The system provides a unified interface for loading and saving secrets, whether they're stored in SOPS-encrypted files, HashiCorp Vault, AWS Secrets Manager, or other systems.

## Architecture

### Core Components

```
SecretManager (Facade)
    │
    ├── Uses: SecretProvider (Abstract Interface)
    │           │
    │           ├── SopsSecretProvider (Default)
    │           ├── VaultSecretProvider (Future)
    │           ├── AWSSecretsProvider (Future)
    │           └── Custom implementations...
    │
    └── Manages: Per-environment secret locations
```

### Key Design Principles

1. **Dependency Injection**: Providers are injected into SecretManager
2. **Interface Segregation**: Simple load/save interface
3. **Environment Isolation**: Each environment has its own secret namespace
4. **Backend Agnostic**: Application code doesn't know about storage details

## The SecretProvider Interface

All secret providers implement this simple interface:

```python
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

class SecretProvider(ABC):
    """Abstract base class for secret providers."""

    @abstractmethod
    def load_secret(self, location: str | Path) -> dict[str, Any]:
        """Load a secret from a location.

        Args:
            location: Provider-specific location identifier
                - SOPS: File path (e.g., "envs/dev/proxmox.yaml")
                - Vault: Secret path (e.g., "secret/data/dev/proxmox")
                - AWS: Secret ARN or name

        Returns:
            Secret data as dictionary

        Raises:
            SecretError: If secret cannot be loaded
        """
        pass

    @abstractmethod
    def save_secret(self, location: str | Path, data: dict[str, Any]) -> None:
        """Save a secret to a location.

        Args:
            location: Provider-specific location identifier
            data: Secret data to save

        Raises:
            SecretError: If secret cannot be saved
        """
        pass
```

## Built-in Providers

### SopsSecretProvider (Default)

Uses Mozilla SOPS with age encryption for file-based secrets.

**Features:**
- ✅ File-based storage (git-friendly when encrypted)
- ✅ Age encryption (modern, secure)
- ✅ Per-environment keys
- ✅ No external dependencies

**Location Format:** File paths
```python
provider.load_secret("envs/dev/proxmox.yaml")
```

**Configuration:**
```python
from infrafoundry.core.secrets import SecretManager
from infrafoundry.core.secrets.providers.sops import SopsSecretProvider

# Uses SOPS by default
manager = SecretManager(env_name="dev")

# Or explicitly
manager = SecretManager(
    env_name="dev",
    provider=SopsSecretProvider()
)
```

## Implementing Custom Providers

### Example: HashiCorp Vault Provider

```python
# src/infrafoundry/core/secrets/providers/vault.py
import hvac
from pathlib import Path
from typing import Any

from infrafoundry.core.exceptions import SecretError, SecretNotFoundError
from infrafoundry.core.secrets.provider import SecretProvider


class VaultSecretProvider(SecretProvider):
    """Secret provider using HashiCorp Vault."""

    def __init__(
        self,
        vault_addr: str | None = None,
        vault_token: str | None = None,
        mount_point: str = "secret",
    ):
        """Initialize Vault provider.

        Args:
            vault_addr: Vault server address (defaults to VAULT_ADDR env var)
            vault_token: Vault token (defaults to VAULT_TOKEN env var)
            mount_point: KV mount point (default: "secret")
        """
        import os

        self.vault_addr = vault_addr or os.getenv("VAULT_ADDR")
        self.vault_token = vault_token or os.getenv("VAULT_TOKEN")
        self.mount_point = mount_point

        if not self.vault_addr:
            raise SecretError("VAULT_ADDR not set")
        if not self.vault_token:
            raise SecretError("VAULT_TOKEN not set")

        try:
            self.client = hvac.Client(
                url=self.vault_addr,
                token=self.vault_token
            )
            if not self.client.is_authenticated():
                raise SecretError("Vault authentication failed")
        except Exception as e:
            raise SecretError(f"Failed to connect to Vault: {e}") from e

    def load_secret(self, location: str | Path) -> dict[str, Any]:
        """Load secret from Vault.

        Args:
            location: Vault secret path (e.g., "dev/proxmox")

        Returns:
            Secret data
        """
        path = str(location)

        try:
            # KV v2 API
            response = self.client.secrets.kv.v2.read_secret_version(
                path=path,
                mount_point=self.mount_point
            )
            return response['data']['data']

        except hvac.exceptions.InvalidPath:
            raise SecretNotFoundError(f"Secret not found: {path}")
        except Exception as e:
            raise SecretError(f"Failed to load secret from Vault: {e}") from e

    def save_secret(self, location: str | Path, data: dict[str, Any]) -> None:
        """Save secret to Vault.

        Args:
            location: Vault secret path
            data: Secret data to save
        """
        path = str(location)

        try:
            self.client.secrets.kv.v2.create_or_update_secret(
                path=path,
                secret=data,
                mount_point=self.mount_point
            )
        except Exception as e:
            raise SecretError(f"Failed to save secret to Vault: {e}") from e
```

### Usage

```python
from infrafoundry.core.secrets import SecretManager
from infrafoundry.core.secrets.providers.vault import VaultSecretProvider

# Configure Vault provider
vault_provider = VaultSecretProvider(
    vault_addr="https://vault.company.com",
    vault_token="s.abc123...",
    mount_point="infrafoundry"
)

# Inject into SecretManager
manager = SecretManager(
    env_name="prod",
    provider=vault_provider
)

# Use normally - SecretManager handles the rest
secrets = manager.decrypt_file("proxmox")  # Loads from vault://infrafoundry/data/prod/proxmox
```

### Example: AWS Secrets Manager Provider

```python
# src/infrafoundry/core/secrets/providers/aws_secrets.py
import json
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import ClientError

from infrafoundry.core.exceptions import SecretError, SecretNotFoundError
from infrafoundry.core.secrets.provider import SecretProvider


class AWSSecretsProvider(SecretProvider):
    """Secret provider using AWS Secrets Manager."""

    def __init__(self, region_name: str = "us-east-1", prefix: str = "infrafoundry"):
        """Initialize AWS Secrets Manager provider.

        Args:
            region_name: AWS region
            prefix: Secret name prefix (default: "infrafoundry")
        """
        self.region_name = region_name
        self.prefix = prefix
        self.client = boto3.client('secretsmanager', region_name=region_name)

    def _build_secret_name(self, location: str | Path) -> str:
        """Build AWS secret name from location.

        Args:
            location: Environment-relative path (e.g., "dev/proxmox")

        Returns:
            Full secret name (e.g., "infrafoundry/dev/proxmox")
        """
        return f"{self.prefix}/{location}"

    def load_secret(self, location: str | Path) -> dict[str, Any]:
        """Load secret from AWS Secrets Manager.

        Args:
            location: Secret location (e.g., "dev/proxmox")

        Returns:
            Secret data as dictionary
        """
        secret_name = self._build_secret_name(location)

        try:
            response = self.client.get_secret_value(SecretId=secret_name)
            secret_string = response['SecretString']
            return json.loads(secret_string)

        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                raise SecretNotFoundError(f"Secret not found: {secret_name}")
            raise SecretError(f"Failed to load secret: {e}") from e
        except Exception as e:
            raise SecretError(f"Unexpected error loading secret: {e}") from e

    def save_secret(self, location: str | Path, data: dict[str, Any]) -> None:
        """Save secret to AWS Secrets Manager.

        Args:
            location: Secret location
            data: Secret data to save
        """
        secret_name = self._build_secret_name(location)
        secret_string = json.dumps(data)

        try:
            # Try to update existing secret
            self.client.update_secret(
                SecretId=secret_name,
                SecretString=secret_string
            )
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                # Create new secret
                self.client.create_secret(
                    Name=secret_name,
                    SecretString=secret_string,
                    Description=f"InfraFoundry secret: {location}"
                )
            else:
                raise SecretError(f"Failed to save secret: {e}") from e
```

### Example: 1Password Provider

```python
# src/infrafoundry/core/secrets/providers/onepassword.py
import json
import subprocess
from pathlib import Path
from typing import Any

from infrafoundry.core.exceptions import SecretError, SecretNotFoundError
from infrafoundry.core.secrets.provider import SecretProvider


class OnePasswordProvider(SecretProvider):
    """Secret provider using 1Password CLI."""

    def __init__(self, vault: str = "Infrastructure"):
        """Initialize 1Password provider.

        Args:
            vault: 1Password vault name
        """
        self.vault = vault
        self._check_cli_installed()

    def _check_cli_installed(self) -> None:
        """Verify op CLI is installed and authenticated."""
        try:
            subprocess.run(
                ["op", "account", "get"],
                capture_output=True,
                check=True
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise SecretError(
                "1Password CLI not found or not authenticated. "
                "Install: https://developer.1password.com/docs/cli/get-started/"
            )

    def load_secret(self, location: str | Path) -> dict[str, Any]:
        """Load secret from 1Password.

        Args:
            location: Item name in 1Password (e.g., "dev-proxmox")

        Returns:
            Secret data from item's fields
        """
        item_name = str(location)

        try:
            # Get item as JSON
            result = subprocess.run(
                ["op", "item", "get", item_name, "--vault", self.vault, "--format", "json"],
                capture_output=True,
                check=True,
                text=True
            )

            item = json.loads(result.stdout)

            # Extract fields into dict
            data = {}
            for field in item.get('fields', []):
                if field.get('value'):
                    data[field['label']] = field['value']

            return data

        except subprocess.CalledProcessError as e:
            if "not found" in e.stderr.lower():
                raise SecretNotFoundError(f"1Password item not found: {item_name}")
            raise SecretError(f"Failed to load from 1Password: {e.stderr}") from e
        except Exception as e:
            raise SecretError(f"Unexpected error: {e}") from e

    def save_secret(self, location: str | Path, data: dict[str, Any]) -> None:
        """Save secret to 1Password.

        Args:
            location: Item name
            data: Secret data (keys become field labels)
        """
        item_name = str(location)

        # Build field arguments
        fields = []
        for key, value in data.items():
            fields.extend([f"{key}[password]={value}"])

        try:
            # Create or update item
            subprocess.run(
                ["op", "item", "create",
                 "--category", "password",
                 "--vault", self.vault,
                 "--title", item_name,
                 *fields],
                capture_output=True,
                check=True
            )
        except subprocess.CalledProcessError as e:
            raise SecretError(f"Failed to save to 1Password: {e.stderr}") from e
```

## SecretManager Usage

The `SecretManager` class provides a high-level interface regardless of the provider:

```python
from infrafoundry.core.secrets import SecretManager

# Initialize with environment
manager = SecretManager(env_name="dev")

# Load secrets
proxmox_secrets = manager.decrypt_file("proxmox.yaml")
api_token = manager.get_secret("proxmox.yaml", "api.token")

# Save secrets
manager.encrypt_file("new-service.yaml", {
    "api_url": "https://service.example.com",
    "api_key": "secret-key-here"
})

# Export for runners
manager.export_for_terraform("proxmox.yaml", Path("generated/dev/terraform.tfvars"))
manager.export_for_ansible("proxmox.yaml", Path("generated/dev/ansible-vars.yaml"))
```

## Configuration Patterns

### Pattern 1: Environment Variable Selection

```python
import os
from infrafoundry.core.secrets import SecretManager
from infrafoundry.core.secrets.providers.sops import SopsSecretProvider
from infrafoundry.core.secrets.providers.vault import VaultSecretProvider

def create_secret_manager(env_name: str) -> SecretManager:
    """Factory function to create SecretManager with appropriate provider."""

    provider_type = os.getenv("INFRAFOUNDRY_SECRET_PROVIDER", "sops")

    if provider_type == "vault":
        provider = VaultSecretProvider()
    elif provider_type == "aws":
        from infrafoundry.core.secrets.providers.aws_secrets import AWSSecretsProvider
        provider = AWSSecretsProvider()
    elif provider_type == "sops":
        provider = SopsSecretProvider()
    else:
        raise ValueError(f"Unknown secret provider: {provider_type}")

    return SecretManager(env_name=env_name, provider=provider)
```

### Pattern 2: Per-Environment Providers

```python
def create_secret_manager(env_name: str) -> SecretManager:
    """Use different providers for different environments."""

    # Development: Local SOPS files
    if env_name == "dev":
        provider = SopsSecretProvider()

    # Production: External vault
    elif env_name == "prod":
        provider = VaultSecretProvider(
            vault_addr=os.getenv("PROD_VAULT_ADDR"),
            vault_token=os.getenv("PROD_VAULT_TOKEN")
        )

    # Staging: AWS Secrets Manager
    elif env_name == "staging":
        from infrafoundry.core.secrets.providers.aws_secrets import AWSSecretsProvider
        provider = AWSSecretsProvider(region_name="us-west-2")

    return SecretManager(env_name=env_name, provider=provider)
```

### Pattern 3: Configuration File

```yaml
# infrafoundry.yaml
secrets:
  provider: vault

  providers:
    vault:
      address: https://vault.company.com
      mount_point: infrafoundry
      auth_method: token  # or kubernetes, approle, etc.

    aws:
      region: us-east-1
      prefix: infrafoundry

    sops:
      default: true
```

```python
import yaml
from pathlib import Path

def load_secret_provider_config() -> dict:
    """Load secret provider configuration."""
    config_file = Path("infrafoundry.yaml")
    if config_file.exists():
        with open(config_file) as f:
            config = yaml.safe_load(f)
            return config.get('secrets', {})
    return {}

def create_secret_manager(env_name: str) -> SecretManager:
    """Create SecretManager from configuration file."""
    config = load_secret_provider_config()
    provider_name = config.get('provider', 'sops')
    provider_config = config.get('providers', {}).get(provider_name, {})

    if provider_name == 'vault':
        provider = VaultSecretProvider(
            vault_addr=provider_config['address'],
            mount_point=provider_config.get('mount_point', 'secret')
        )
    # ... other providers

    return SecretManager(env_name=env_name, provider=provider)
```

## Migration Guide

### Migrating from SOPS to Vault

**Step 1: Export existing secrets**

```bash
# Export all secrets to JSON
for env in dev staging prod; do
    for file in envs/$env/*.yaml; do
        basename=$(basename $file .yaml)
        sops --decrypt $file > /tmp/${env}-${basename}.json
    done
done
```

**Step 2: Import to Vault**

```bash
# Import to Vault
for env in dev staging prod; do
    for file in /tmp/${env}-*.json; do
        basename=$(basename $file .json | sed "s/^${env}-//")
        vault kv put infrafoundry/data/${env}/${basename} @${file}
    done
done
```

**Step 3: Update InfraFoundry configuration**

```python
# Before (SOPS)
manager = SecretManager(env_name="dev")

# After (Vault)
from infrafoundry.core.secrets.providers.vault import VaultSecretProvider

manager = SecretManager(
    env_name="dev",
    provider=VaultSecretProvider()
)
```

**Step 4: Test**

```python
# Verify secrets load correctly
secrets = manager.decrypt_file("proxmox")
assert secrets['api_url'] == 'https://proxmox.example.com'
```

**Step 5: Clean up old files**

```bash
# After verification, remove SOPS files
# Keep age keys as backup initially
git rm envs/*/proxmox.yaml envs/*/opnsense.yaml
git commit -m "Migrate to Vault secret storage"
```

## Testing Custom Providers

```python
# tests/unit/test_vault_provider.py
import pytest
from unittest.mock import Mock, patch
from infrafoundry.core.secrets.providers.vault import VaultSecretProvider
from infrafoundry.core.exceptions import SecretNotFoundError

@pytest.fixture
def vault_provider():
    """Create VaultSecretProvider with mocked client."""
    with patch('hvac.Client') as mock_client:
        mock_client.return_value.is_authenticated.return_value = True
        provider = VaultSecretProvider(
            vault_addr="http://localhost:8200",
            vault_token="test-token"
        )
        provider.client = mock_client.return_value
        yield provider

def test_load_secret_success(vault_provider):
    """Test loading secret from Vault."""
    # Mock Vault response
    vault_provider.client.secrets.kv.v2.read_secret_version.return_value = {
        'data': {
            'data': {
                'api_url': 'https://example.com',
                'api_token': 'secret-token'
            }
        }
    }

    # Load secret
    data = vault_provider.load_secret("dev/proxmox")

    # Verify
    assert data['api_url'] == 'https://example.com'
    assert data['api_token'] == 'secret-token'

def test_load_secret_not_found(vault_provider):
    """Test SecretNotFoundError is raised."""
    import hvac.exceptions

    vault_provider.client.secrets.kv.v2.read_secret_version.side_effect = \
        hvac.exceptions.InvalidPath()

    with pytest.raises(SecretNotFoundError):
        vault_provider.load_secret("dev/nonexistent")
```

## Best Practices

### 1. Provider Selection

**Use SOPS when:**
- Small team (< 5 people)
- Simple infrastructure
- Want git-based workflows
- No budget for external services

**Use Vault when:**
- Large team with RBAC requirements
- Dynamic secrets needed
- Audit logging required
- Multi-cloud deployments

**Use Cloud Provider (AWS/Azure) when:**
- Already using that cloud
- Want managed service
- Compliance requirements
- Auto-rotation needed

### 2. Security Considerations

**Always:**
- Use environment variables for provider credentials
- Never commit provider tokens/passwords
- Rotate credentials regularly
- Use least-privilege access
- Enable audit logging

**Example:**
```python
# Good - credentials from environment
provider = VaultSecretProvider(
    vault_addr=os.getenv("VAULT_ADDR"),
    vault_token=os.getenv("VAULT_TOKEN")
)

# Bad - hardcoded credentials
provider = VaultSecretProvider(
    vault_addr="https://vault.example.com",
    vault_token="s.abc123..."  # NEVER DO THIS
)
```

### 3. Error Handling

```python
from infrafoundry.core.exceptions import (
    SecretError,
    SecretNotFoundError,
    SecretDecryptionError
)

try:
    secrets = manager.decrypt_file("proxmox.yaml")
except SecretNotFoundError:
    # Secret doesn't exist - might be first run
    logger.warning("Secret not found, using defaults")
    secrets = {}
except SecretDecryptionError as e:
    # Wrong key or corrupted secret
    logger.error(f"Failed to decrypt: {e}")
    raise
except SecretError as e:
    # Generic secret error (network, permissions, etc.)
    logger.error(f"Secret error: {e}")
    raise
```

### 4. Testing

**Mock the provider, not the manager:**

```python
# Good - mock at provider level
def test_deployment(mock_vault_provider):
    manager = SecretManager(env_name="test", provider=mock_vault_provider)
    orchestrator = Orchestrator(secret_manager=manager)
    # Test orchestrator logic

# Bad - mock SecretManager itself
def test_deployment(mock_secret_manager):
    # Loses provider abstraction benefits
```

## CLI Integration

```python
# cli/commands/secrets.py
import click
from infrafoundry.core.secrets import SecretManager

@click.group()
def secrets():
    """Manage infrastructure secrets."""
    pass

@secrets.command()
@click.argument('filename')
@click.argument('key')
@click.option('--env', default='dev', help='Environment name')
def get(filename, key, env):
    """Get a secret value."""
    manager = SecretManager(env_name=env)
    value = manager.get_secret(filename, key)
    click.echo(value)

@secrets.command()
@click.argument('filename')
@click.argument('key')
@click.argument('value')
@click.option('--env', default='dev', help='Environment name')
def set(filename, key, value, env):
    """Set a secret value."""
    manager = SecretManager(env_name=env)

    # Load existing secrets
    try:
        data = manager.decrypt_file(filename)
    except SecretNotFoundError:
        data = {}

    # Update value
    keys = key.split('.')
    current = data
    for k in keys[:-1]:
        current = current.setdefault(k, {})
    current[keys[-1]] = value

    # Save back
    manager.encrypt_file(filename, data)
    click.echo(f"✓ Set {key} in {filename}")
```

**Usage:**
```bash
# Get secret
infra secrets get proxmox.yaml api.token --env prod

# Set secret
infra secrets set proxmox.yaml api.token "new-token-value" --env prod

# Works with any provider (SOPS, Vault, AWS, etc.)
```

## Future Enhancements

### Planned Features

1. **Secret Versioning**
   - Track secret changes over time
   - Rollback to previous versions
   - Audit trail

2. **Dynamic Secrets**
   - Generate credentials on-demand
   - Auto-rotation support
   - Lease management

3. **Secret Templates**
   - Reference other secrets
   - Environment variable substitution
   - Computed values

4. **Caching Layer**
   - Cache decrypted secrets
   - Configurable TTL
   - Reduce provider API calls

### Example: Secret Versioning

```python
class VersionedSecretProvider(SecretProvider):
    """Provider wrapper that adds versioning."""

    def __init__(self, base_provider: SecretProvider):
        self.base_provider = base_provider
        self.versions: dict[str, list[dict]] = {}

    def load_secret(self, location: str | Path) -> dict[str, Any]:
        """Load latest version of secret."""
        return self.base_provider.load_secret(location)

    def load_secret_version(self, location: str | Path, version: int) -> dict[str, Any]:
        """Load specific version."""
        versions = self.versions.get(str(location), [])
        if version >= len(versions):
            raise SecretNotFoundError(f"Version {version} not found")
        return versions[version]

    def save_secret(self, location: str | Path, data: dict[str, Any]) -> None:
        """Save new version of secret."""
        # Save to base provider
        self.base_provider.save_secret(location, data)

        # Track version
        location_str = str(location)
        if location_str not in self.versions:
            self.versions[location_str] = []
        self.versions[location_str].append(data.copy())
```

## References

- [SecretProvider Interface](../../src/infrafoundry/core/secrets/provider.py)
- [SopsSecretProvider Implementation](../../src/infrafoundry/core/secrets/providers/sops.py)
- [SecretManager](../../src/infrafoundry/core/secrets/secret_manager.py)
- [Age Key Management](../age-key-management.md)
- [Per-Environment Credentials](../per-environment-credentials.md)
