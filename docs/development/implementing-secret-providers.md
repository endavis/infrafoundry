# Implementing Custom Secret Providers

**Audience:** Developers extending InfraFoundry
**Difficulty:** Intermediate
**Time:** 30-60 minutes

## Quick Start

Want to integrate InfraFoundry with your secret backend? Follow this guide to implement a custom `SecretProvider`.

### 1. Create Provider File

```bash
# Create provider file
touch src/infrafoundry/core/secrets/providers/my_vault.py
```

### 2. Implement Interface

```python
from pathlib import Path
from typing import Any

from infrafoundry.core.exceptions import SecretError, SecretNotFoundError
from infrafoundry.core.secrets.provider import SecretProvider


class MyVaultProvider(SecretProvider):
    """Secret provider for MyVault system."""

    def __init__(self, api_url: str, api_key: str):
        """Initialize provider with connection details."""
        self.api_url = api_url
        self.api_key = api_key
        # Initialize client, test connection, etc.

    def load_secret(self, location: str | Path) -> dict[str, Any]:
        """Load secret from MyVault."""
        # 1. Convert location to vault path
        # 2. Call vault API
        # 3. Return dict
        # 4. Raise SecretNotFoundError if not exists
        # 5. Raise SecretError for other errors
        pass

    def save_secret(self, location: str | Path, data: dict[str, Any]) -> None:
        """Save secret to MyVault."""
        # 1. Convert location to vault path
        # 2. Call vault API to create/update
        # 3. Raise SecretError on failure
        pass
```

### 3. Use Your Provider

```python
from infrafoundry.core.secrets import SecretManager
from infrafoundry.core.secrets.providers.my_vault import MyVaultProvider

provider = MyVaultProvider(
    api_url="https://vault.company.com",
    api_key=os.getenv("MY_VAULT_KEY")
)

manager = SecretManager(env_name="dev", provider=provider)
```

That's it! Your provider now works with all InfraFoundry features.

## Complete Implementation Guide

### Step 1: Understand the Interface

The `SecretProvider` interface has only two required methods:

```python
class SecretProvider(ABC):
    @abstractmethod
    def load_secret(self, location: str | Path) -> dict[str, Any]:
        """Load a secret from storage."""
        pass

    @abstractmethod
    def save_secret(self, location: str | Path, data: dict[str, Any]) -> None:
        """Save a secret to storage."""
        pass
```

**Key points:**
- `location` is flexible - interpret it how makes sense for your backend
- Always return `dict[str, Any]` from `load_secret`
- Raise `SecretNotFoundError` when secret doesn't exist
- Raise `SecretError` for other errors
- `save_secret` should create or update

### Step 2: Design Location Mapping

Decide how to map InfraFoundry's locations to your backend's paths.

**Example: File-based (SOPS)**
```
location: "proxmox.yaml"
→ file: envs/dev/proxmox.yaml
```

**Example: Vault**
```
location: "proxmox"
→ path: secret/data/dev/proxmox
```

**Example: AWS Secrets Manager**
```
location: "proxmox"
→ name: infrafoundry/dev/proxmox
```

**Pattern:**
```python
def _build_path(self, location: str | Path) -> str:
    """Convert InfraFoundry location to backend-specific path."""
    # Add prefixes, formatting, etc.
    return f"{self.prefix}/{self.env}/{location}"
```

### Step 3: Implement load_secret

```python
def load_secret(self, location: str | Path) -> dict[str, Any]:
    """Load secret from backend.

    Args:
        location: InfraFoundry secret location

    Returns:
        Secret data as dictionary

    Raises:
        SecretNotFoundError: Secret doesn't exist
        SecretError: Connection, auth, or other errors
    """
    # 1. Build backend-specific path
    path = self._build_path(location)

    try:
        # 2. Call backend API/SDK
        response = self.client.get_secret(path)

        # 3. Extract data (format varies by backend)
        data = response['data']  # Adjust for your backend

        # 4. Return as dict
        return data

    except BackendNotFoundError:
        # 5. Map backend's "not found" to SecretNotFoundError
        raise SecretNotFoundError(f"Secret not found: {path}")

    except BackendAuthError as e:
        # 6. Map backend auth errors to SecretError
        raise SecretError(f"Authentication failed: {e}") from e

    except Exception as e:
        # 7. Catch all other errors
        raise SecretError(f"Failed to load secret: {e}") from e
```

**Error handling is critical:**
- Always distinguish "not found" from other errors
- Provide helpful error messages
- Chain exceptions with `from e` for debugging

### Step 4: Implement save_secret

```python
def save_secret(self, location: str | Path, data: dict[str, Any]) -> None:
    """Save secret to backend.

    Args:
        location: Where to save secret
        data: Secret data (must be dict)

    Raises:
        SecretError: If save fails
    """
    path = self._build_path(location)

    try:
        # Try to update existing secret
        self.client.update_secret(path, data)

    except BackendNotFoundError:
        # Create new secret if doesn't exist
        self.client.create_secret(path, data)

    except Exception as e:
        raise SecretError(f"Failed to save secret: {e}") from e
```

**Idempotent saves:**
- `save_secret` should create or update
- Don't fail if secret already exists
- Don't fail if secret doesn't exist yet

### Step 5: Add Initialization & Configuration

```python
def __init__(
    self,
    api_url: str | None = None,
    api_key: str | None = None,
    timeout: int = 30,
):
    """Initialize provider.

    Args:
        api_url: Backend API URL (defaults to ENV_VAR)
        api_key: API key (defaults to ENV_VAR)
        timeout: Request timeout in seconds
    """
    import os

    # 1. Support environment variables
    self.api_url = api_url or os.getenv("MY_VAULT_URL")
    self.api_key = api_key or os.getenv("MY_VAULT_KEY")

    # 2. Validate required config
    if not self.api_url:
        raise SecretError("MY_VAULT_URL not configured")
    if not self.api_key:
        raise SecretError("MY_VAULT_KEY not configured")

    # 3. Initialize client
    try:
        self.client = BackendClient(
            url=self.api_url,
            api_key=self.api_key,
            timeout=timeout
        )
    except Exception as e:
        raise SecretError(f"Failed to initialize client: {e}") from e

    # 4. Test connection (optional but recommended)
    try:
        self.client.health_check()
    except Exception as e:
        raise SecretError(f"Backend health check failed: {e}") from e
```

### Step 6: Add Tests

```python
# tests/unit/test_my_vault_provider.py
import pytest
from unittest.mock import Mock, patch
from infrafoundry.core.secrets.providers.my_vault import MyVaultProvider
from infrafoundry.core.exceptions import SecretNotFoundError, SecretError


@pytest.fixture
def mock_client():
    """Mock backend client."""
    with patch('my_vault_sdk.Client') as mock:
        yield mock.return_value


@pytest.fixture
def provider(mock_client):
    """Create provider with mocked client."""
    provider = MyVaultProvider(
        api_url="https://vault.test",
        api_key="test-key"
    )
    provider.client = mock_client
    return provider


def test_load_secret_success(provider, mock_client):
    """Test successful secret loading."""
    # Arrange
    mock_client.get_secret.return_value = {
        'data': {
            'api_url': 'https://example.com',
            'api_token': 'secret'
        }
    }

    # Act
    result = provider.load_secret("test-secret")

    # Assert
    assert result == {
        'api_url': 'https://example.com',
        'api_token': 'secret'
    }
    mock_client.get_secret.assert_called_once()


def test_load_secret_not_found(provider, mock_client):
    """Test SecretNotFoundError is raised."""
    # Arrange
    from my_vault_sdk import NotFoundError
    mock_client.get_secret.side_effect = NotFoundError()

    # Act & Assert
    with pytest.raises(SecretNotFoundError, match="not found"):
        provider.load_secret("nonexistent")


def test_save_secret_creates_new(provider, mock_client):
    """Test saving new secret."""
    # Arrange
    from my_vault_sdk import NotFoundError
    mock_client.update_secret.side_effect = NotFoundError()

    data = {'key': 'value'}

    # Act
    provider.save_secret("new-secret", data)

    # Assert
    mock_client.create_secret.assert_called_once()


def test_save_secret_updates_existing(provider, mock_client):
    """Test updating existing secret."""
    # Arrange
    data = {'key': 'new-value'}

    # Act
    provider.save_secret("existing-secret", data)

    # Assert
    mock_client.update_secret.assert_called_once()
    mock_client.create_secret.assert_not_called()


def test_initialization_missing_url(monkeypatch):
    """Test error when URL not configured."""
    monkeypatch.delenv("MY_VAULT_URL", raising=False)

    with pytest.raises(SecretError, match="not configured"):
        MyVaultProvider(api_key="test")


def test_connection_failure(mock_client):
    """Test error on connection failure."""
    mock_client.side_effect = ConnectionError("Network error")

    with pytest.raises(SecretError, match="Failed to initialize"):
        MyVaultProvider(
            api_url="https://vault.test",
            api_key="test-key"
        )
```

## Real-World Examples

### Example 1: Redis-based Provider

```python
# For fast, ephemeral secrets (dev environments, caching)
import json
import redis
from typing import Any
from pathlib import Path

from infrafoundry.core.exceptions import SecretError, SecretNotFoundError
from infrafoundry.core.secrets.provider import SecretProvider


class RedisSecretProvider(SecretProvider):
    """Ephemeral secret storage using Redis."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        prefix: str = "infra:secrets",
        ttl: int | None = None,
    ):
        """Initialize Redis provider.

        Args:
            host: Redis host
            port: Redis port
            db: Redis database number
            prefix: Key prefix for all secrets
            ttl: Optional TTL in seconds
        """
        self.prefix = prefix
        self.ttl = ttl

        try:
            self.client = redis.Redis(
                host=host,
                port=port,
                db=db,
                decode_responses=True
            )
            # Test connection
            self.client.ping()
        except Exception as e:
            raise SecretError(f"Failed to connect to Redis: {e}") from e

    def _build_key(self, location: str | Path) -> str:
        """Build Redis key from location."""
        return f"{self.prefix}:{location}"

    def load_secret(self, location: str | Path) -> dict[str, Any]:
        """Load secret from Redis."""
        key = self._build_key(location)

        try:
            data = self.client.get(key)
            if data is None:
                raise SecretNotFoundError(f"Secret not found: {location}")

            return json.loads(data)

        except SecretNotFoundError:
            raise
        except Exception as e:
            raise SecretError(f"Failed to load from Redis: {e}") from e

    def save_secret(self, location: str | Path, data: dict[str, Any]) -> None:
        """Save secret to Redis with optional TTL."""
        key = self._build_key(location)

        try:
            json_data = json.dumps(data)

            if self.ttl:
                self.client.setex(key, self.ttl, json_data)
            else:
                self.client.set(key, json_data)

        except Exception as e:
            raise SecretError(f"Failed to save to Redis: {e}") from e
```

**Use case:** Development environments where secrets don't need persistence:

```python
# Dev environment - ephemeral secrets
provider = RedisSecretProvider(ttl=3600)  # 1 hour TTL
manager = SecretManager(env_name="dev", provider=provider)
```

### Example 2: Bitwarden Provider

```python
# Using Bitwarden CLI for team secret management
import json
import subprocess
from pathlib import Path
from typing import Any

from infrafoundry.core.exceptions import SecretError, SecretNotFoundError
from infrafoundry.core.secrets.provider import SecretProvider


class BitwardenProvider(SecretProvider):
    """Secret provider using Bitwarden CLI."""

    def __init__(self, organization_id: str | None = None):
        """Initialize Bitwarden provider.

        Args:
            organization_id: Optional organization/collection ID
        """
        self.organization_id = organization_id
        self._check_authenticated()

    def _check_authenticated(self) -> None:
        """Verify bw CLI is installed and unlocked."""
        try:
            result = subprocess.run(
                ["bw", "status"],
                capture_output=True,
                check=True,
                text=True
            )
            status = json.loads(result.stdout)

            if status['status'] != 'unlocked':
                raise SecretError(
                    "Bitwarden vault is locked. Run: bw unlock"
                )

        except FileNotFoundError:
            raise SecretError(
                "Bitwarden CLI not found. "
                "Install: https://bitwarden.com/help/cli/"
            )
        except Exception as e:
            raise SecretError(f"Bitwarden check failed: {e}") from e

    def load_secret(self, location: str | Path) -> dict[str, Any]:
        """Load secret from Bitwarden item."""
        item_name = str(location)

        try:
            # Search for item
            result = subprocess.run(
                ["bw", "get", "item", item_name],
                capture_output=True,
                check=True,
                text=True
            )

            item = json.loads(result.stdout)

            # Extract fields into dict
            data = {}

            # Login fields
            if item.get('login'):
                login = item['login']
                if login.get('username'):
                    data['username'] = login['username']
                if login.get('password'):
                    data['password'] = login['password']

            # Custom fields
            for field in item.get('fields', []):
                if field.get('name') and field.get('value'):
                    data[field['name']] = field['value']

            # Notes as JSON (optional)
            if item.get('notes'):
                try:
                    notes_data = json.loads(item['notes'])
                    data.update(notes_data)
                except json.JSONDecodeError:
                    data['notes'] = item['notes']

            return data

        except subprocess.CalledProcessError as e:
            if "Not found" in e.stderr:
                raise SecretNotFoundError(f"Item not found: {item_name}")
            raise SecretError(f"Bitwarden error: {e.stderr}") from e
        except Exception as e:
            raise SecretError(f"Failed to load secret: {e}") from e

    def save_secret(self, location: str | Path, data: dict[str, Any]) -> None:
        """Save secret as Bitwarden item.

        Creates a secure note with JSON in notes field.
        """
        item_name = str(location)

        # Build item JSON
        item = {
            "organizationId": self.organization_id,
            "type": 2,  # Secure note
            "name": item_name,
            "notes": json.dumps(data, indent=2),
            "secureNote": {"type": 0}
        }

        try:
            # Encode item for bw CLI
            item_json = json.dumps(item)

            # Create item
            subprocess.run(
                ["bw", "create", "item", item_json],
                capture_output=True,
                check=True,
                text=True,
                input=item_json
            )

        except subprocess.CalledProcessError as e:
            if "already exists" in e.stderr.lower():
                # Update instead
                self._update_item(item_name, data)
            else:
                raise SecretError(f"Failed to save: {e.stderr}") from e

    def _update_item(self, item_name: str, data: dict[str, Any]) -> None:
        """Update existing Bitwarden item."""
        # Get item ID
        result = subprocess.run(
            ["bw", "get", "item", item_name],
            capture_output=True,
            check=True,
            text=True
        )
        item = json.loads(result.stdout)
        item_id = item['id']

        # Update notes
        item['notes'] = json.dumps(data, indent=2)

        # Encode and edit
        item_json = json.dumps(item)
        subprocess.run(
            ["bw", "edit", "item", item_id, item_json],
            capture_output=True,
            check=True,
            text=True
        )
```

### Example 3: Multi-Provider (Fallback Chain)

```python
# Try multiple providers in order
from typing import Any
from pathlib import Path

from infrafoundry.core.exceptions import SecretError, SecretNotFoundError
from infrafoundry.core.secrets.provider import SecretProvider


class FallbackProvider(SecretProvider):
    """Try multiple providers in order until one succeeds."""

    def __init__(self, *providers: SecretProvider):
        """Initialize with prioritized list of providers.

        Args:
            *providers: Providers to try in order
        """
        if not providers:
            raise ValueError("At least one provider required")
        self.providers = providers

    def load_secret(self, location: str | Path) -> dict[str, Any]:
        """Try each provider until one succeeds."""
        errors = []

        for i, provider in enumerate(self.providers):
            try:
                return provider.load_secret(location)
            except SecretNotFoundError:
                # Try next provider
                continue
            except Exception as e:
                # Log error but continue
                errors.append(f"Provider {i}: {e}")
                continue

        # All providers failed
        raise SecretNotFoundError(
            f"Secret not found in any provider: {location}. "
            f"Errors: {'; '.join(errors)}"
        )

    def save_secret(self, location: str | Path, data: dict[str, Any]) -> None:
        """Save to first provider."""
        # Only save to primary provider
        self.providers[0].save_secret(location, data)
```

**Usage:**
```python
# Try Vault first, fall back to SOPS files
from infrafoundry.core.secrets.providers.vault import VaultProvider
from infrafoundry.core.secrets.providers.sops import SopsSecretProvider

provider = FallbackProvider(
    VaultProvider(),      # Try Vault first (production)
    SopsSecretProvider()  # Fall back to local files (dev)
)

manager = SecretManager(env_name="dev", provider=provider)
```

## Common Patterns

### Pattern 1: Provider Factory

```python
# providers/factory.py
import os
from typing import Literal

from infrafoundry.core.secrets.provider import SecretProvider
from infrafoundry.core.secrets.providers.sops import SopsSecretProvider


ProviderType = Literal["sops", "vault", "aws", "custom"]


def create_provider(
    provider_type: ProviderType = "sops",
    **kwargs
) -> SecretProvider:
    """Factory function to create secret providers.

    Args:
        provider_type: Type of provider to create
        **kwargs: Provider-specific configuration

    Returns:
        Configured SecretProvider instance
    """
    if provider_type == "sops":
        return SopsSecretProvider()

    elif provider_type == "vault":
        from infrafoundry.core.secrets.providers.vault import VaultProvider
        return VaultProvider(
            vault_addr=kwargs.get('vault_addr'),
            vault_token=kwargs.get('vault_token')
        )

    elif provider_type == "aws":
        from infrafoundry.core.secrets.providers.aws import AWSSecretsProvider
        return AWSSecretsProvider(
            region_name=kwargs.get('region', 'us-east-1')
        )

    elif provider_type == "custom":
        # Load custom provider from module path
        module_path = kwargs.get('module')
        class_name = kwargs.get('class')

        import importlib
        module = importlib.import_module(module_path)
        provider_class = getattr(module, class_name)

        return provider_class(**kwargs.get('config', {}))

    else:
        raise ValueError(f"Unknown provider type: {provider_type}")
```

### Pattern 2: Environment-Aware Provider

```python
# Auto-select provider based on environment
def create_env_aware_provider(env_name: str) -> SecretProvider:
    """Create provider appropriate for environment."""

    # Development: local SOPS files
    if env_name in ('dev', 'local'):
        return SopsSecretProvider()

    # CI: Use environment variables
    elif env_name == 'ci':
        return EnvironmentVariableProvider()

    # Staging: AWS Secrets Manager
    elif env_name == 'staging':
        return AWSSecretsProvider(region='us-west-2')

    # Production: HashiCorp Vault
    elif env_name == 'prod':
        return VaultProvider(
            vault_addr=os.getenv('PROD_VAULT_ADDR'),
            vault_token=os.getenv('PROD_VAULT_TOKEN')
        )

    else:
        # Default to SOPS
        return SopsSecretProvider()
```

## Debugging & Troubleshooting

### Enable Debug Logging

```python
import logging

# Enable debug logging for your provider
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('infrafoundry.core.secrets.providers.my_vault')
logger.setLevel(logging.DEBUG)

# Add logging to your provider
class MyVaultProvider(SecretProvider):
    def __init__(self, *args, **kwargs):
        self.logger = logging.getLogger(__name__)
        # ...

    def load_secret(self, location):
        self.logger.debug(f"Loading secret from {location}")
        try:
            # ...
            self.logger.debug(f"Successfully loaded {location}")
        except Exception as e:
            self.logger.error(f"Failed to load {location}: {e}")
            raise
```

### Test with Mock Backend

```python
# Create a fake backend for testing
class MockBackend:
    def __init__(self):
        self.secrets = {}

    def get(self, path):
        if path not in self.secrets:
            raise NotFoundError(path)
        return self.secrets[path]

    def set(self, path, data):
        self.secrets[path] = data

# Use in tests
provider = MyVaultProvider(...)
provider.client = MockBackend()
```

### Common Issues

**Issue: "Secret not found" but it exists**
- Check path/location mapping
- Verify authentication/permissions
- Log the actual path being requested

**Issue: Data format mismatch**
- Ensure `load_secret` returns `dict[str, Any]`
- Check JSON parsing/serialization
- Verify nested structure handling

**Issue: Timeout errors**
- Add configurable timeout
- Implement retry logic
- Add connection pooling

## Checklist for New Providers

Before submitting a provider implementation:

- [ ] Implements `SecretProvider` interface correctly
- [ ] Raises `SecretNotFoundError` when secret doesn't exist
- [ ] Raises `SecretError` for other errors
- [ ] Supports environment variable configuration
- [ ] Has comprehensive tests (>80% coverage)
- [ ] Has docstrings for all public methods
- [ ] Logs debug information
- [ ] Handles connection errors gracefully
- [ ] Is thread-safe (if applicable)
- [ ] Cleans up resources properly
- [ ] Has usage examples in docstring
- [ ] Documents any external dependencies

## Contributing Providers

Want to contribute your provider to InfraFoundry?

1. **Create implementation** in `src/infrafoundry/core/secrets/providers/`
2. **Add tests** in `tests/unit/test_<provider>_provider.py`
3. **Document usage** in provider docstring
4. **Update architecture docs** to list new provider
5. **Submit PR** with:
   - Provider implementation
   - Tests (minimum 80% coverage)
   - Documentation
   - Example usage
   - Dependencies (if any) added to `pyproject.toml`

## References

- [Secrets Architecture](../architecture/secrets-architecture.md)
- [SecretProvider Interface](../../src/infrafoundry/core/secrets/provider.py)
- [SopsSecretProvider Example](../../src/infrafoundry/core/secrets/providers/sops.py)
- [Exception Types](../../src/infrafoundry/core/exceptions.py)
