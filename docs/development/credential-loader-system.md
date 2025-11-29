# Credential Loader System

**Audience:** Developers extending InfraFoundry
**Difficulty:** Intermediate
**Version:** 1.0
**Last Updated:** 2025-11-29

## Overview

The Credential Loader system automatically loads provider credentials from encrypted secret files and makes them available as environment variables. It uses a factory pattern with provider-specific loaders to handle different credential formats and requirements for each infrastructure provider.

## Architecture

```
CredentialLoader (Factory/Coordinator)
    │
    ├── Uses: SecretProvider (for decryption)
    │
    └── Manages: Provider-Specific Loaders
                    │
                    ├── ProxmoxCredentialLoader
                    ├── OPNsenseCredentialLoader
                    ├── KubernetesCredentialLoader
                    └── CustomCredentialLoader (extensible)
```

### Key Components

**CredentialLoader** - Main coordinator class
- Discovers and instantiates provider-specific loaders
- Loads credentials for one or all providers
- Manages environment variables
- Provides context manager for temporary credentials

**BaseCredentialLoader** - Abstract base class for provider loaders
- Defines interface for credential loading
- Handles secret decryption via SecretProvider
- Maps secret keys to environment variable names

**Provider-Specific Loaders** - Concrete implementations
- One per provider (Proxmox, OPNsense, etc.)
- Define credential file name
- Define field mapping (secret keys → env vars)

## How It Works

### 1. Credential Files

Credentials are stored in encrypted YAML files per environment:

```
config-repo/
├── envs/
│   ├── dev/
│   │   ├── proxmox.yaml    # Encrypted with SOPS/age
│   │   ├── opnsense.yaml
│   │   └── age.key
│   └── prod/
│       ├── proxmox.yaml
│       ├── opnsense.yaml
│       └── age.key
```

### 2. Loading Process

```python
# 1. Initialize loader
loader = CredentialLoader(config_dir=Path("/path/to/config"))

# 2. Load credentials for environment
credentials = loader.load("prod")  # Returns dict of env vars

# 3. Apply to environment
loader.apply_to_environment(credentials)

# 4. Now environment variables are set
# PROXMOX_API_URL, PROXMOX_API_TOKEN_ID, etc.
```

### 3. Field Mapping

Each provider loader defines how secret keys map to environment variables:

```python
# In proxmox.yaml (encrypted):
proxmox_api_url: https://proxmox.example.com:8006
proxmox_token_id: root@pam!infra
proxmox_token_secret: abc123...

# Mapped to environment variables:
PROXMOX_API_URL=https://proxmox.example.com:8006
PROXMOX_API_TOKEN_ID=root@pam!infra
PROXMOX_API_TOKEN_SECRET=abc123...
```

## Usage

### Basic Usage

```python
from pathlib import Path
from infrafoundry.core.credential_loader import CredentialLoader

# Initialize
loader = CredentialLoader(config_dir=Path("/path/to/config-repo"))

# Load all providers for environment
credentials = loader.load("dev")

# Apply to current process environment
loader.apply_to_environment(credentials)

# Now use provider SDKs/tools
# They'll read from environment variables
```

### Load Specific Providers

```python
# Only load Proxmox credentials
credentials = loader.load("prod", providers=["proxmox"])

# Load multiple specific providers
credentials = loader.load("dev", providers=["proxmox", "opnsense"])
```

### Context Manager (Temporary Credentials)

```python
# Credentials are set only within the context
with loader.temporary_credentials("prod") as creds:
    # Environment variables are set here
    # PROXMOX_API_URL, etc.
    run_deployment()

# Environment variables are restored to original values
```

### Manual Environment Management

```python
# Save current environment
saved = loader.capture_current_environment()

# Load and apply new credentials
credentials = loader.load("staging")
loader.apply_to_environment(credentials)

# Do work...
run_deployment()

# Restore original environment
loader.restore_environment(saved)
```

## Implementing Custom Loaders

### Step 1: Create Loader Class

```python
# src/infrafoundry/core/credential_loader/aws_loader.py
from typing import override
from infrafoundry.core.credential_loader.base_loader import BaseCredentialLoader


class AWSCredentialLoader(BaseCredentialLoader):
    """Loads AWS-specific credentials."""

    @property
    @override
    def provider_name(self) -> str:
        """Return the provider name."""
        return "aws"

    @property
    @override
    def credential_file(self) -> str:
        """Return the credential filename."""
        return "aws.yaml"

    @property
    @override
    def field_mapping(self) -> dict[str, str]:
        """Return mapping of secret keys to environment variables."""
        return {
            "aws_access_key_id": "AWS_ACCESS_KEY_ID",
            "aws_secret_access_key": "AWS_SECRET_ACCESS_KEY",
            "aws_region": "AWS_DEFAULT_REGION",
            "aws_session_token": "AWS_SESSION_TOKEN",  # Optional
        }
```

### Step 2: Register Loader

```python
# Update src/infrafoundry/core/credential_loader/credential_loader.py
from infrafoundry.core.credential_loader.aws_loader import AWSCredentialLoader

class CredentialLoader:
    PROVIDER_LOADERS = {
        "proxmox": ProxmoxCredentialLoader,
        "opnsense": OPNsenseCredentialLoader,
        "kubernetes": KubernetesCredentialLoader,
        "aws": AWSCredentialLoader,  # Add your loader
    }
```

### Step 3: Create Credential File

```yaml
# envs/prod/aws.yaml (encrypt with SOPS)
aws_access_key_id: AKIAIOSFODNN7EXAMPLE
aws_secret_access_key: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
aws_region: us-west-2
```

```bash
# Encrypt with SOPS
sops --encrypt --in-place envs/prod/aws.yaml
```

### Step 4: Use Your Loader

```python
loader = CredentialLoader()
credentials = loader.load("prod", providers=["aws"])
loader.apply_to_environment(credentials)

# AWS credentials are now available
import boto3
s3 = boto3.client('s3')  # Uses AWS_ACCESS_KEY_ID, etc.
```

## Advanced Patterns

### Pattern 1: Dynamic Field Mapping

For credentials with variable field names:

```python
class DynamicCredentialLoader(BaseCredentialLoader):
    """Loader with dynamic field mapping."""

    @property
    def field_mapping(self) -> dict[str, str]:
        """Return mapping based on configuration."""
        # Could be loaded from config file or environment
        base_mapping = {
            "api_url": "CUSTOM_API_URL",
            "api_key": "CUSTOM_API_KEY",
        }

        # Add optional fields if present
        if self._include_optional():
            base_mapping.update({
                "api_secret": "CUSTOM_API_SECRET",
                "api_region": "CUSTOM_API_REGION",
            })

        return base_mapping

    def _include_optional(self) -> bool:
        """Check if optional fields should be included."""
        # Custom logic here
        return os.getenv("INCLUDE_OPTIONAL_CREDS") == "true"
```

### Pattern 2: Credential Validation

Add validation before returning credentials:

```python
class ValidatedCredentialLoader(BaseCredentialLoader):
    """Loader with credential validation."""

    def load_credentials(self) -> dict[str, str]:
        """Load and validate credentials."""
        credentials = super().load_credentials()

        # Validate required fields
        required = ["API_URL", "API_KEY"]
        missing = [k for k in required if k not in credentials]

        if missing:
            raise CredentialLoaderError(
                f"Missing required credentials for {self.provider_name}: "
                f"{', '.join(missing)}"
            )

        # Validate format
        if not credentials.get("API_URL", "").startswith("https://"):
            raise CredentialLoaderError(
                f"API_URL must start with https:// for {self.provider_name}"
            )

        return credentials
```

### Pattern 3: Fallback Credentials

Try multiple sources in order:

```python
class FallbackCredentialLoader(BaseCredentialLoader):
    """Loader with fallback to environment variables."""

    def load_credentials(self) -> dict[str, str]:
        """Load from file, fall back to environment."""
        # Try loading from encrypted file
        credentials = super().load_credentials()

        # Fall back to environment variables for missing fields
        for secret_key, env_var in self.field_mapping.items():
            if env_var not in credentials:
                if value := os.getenv(env_var):
                    credentials[env_var] = value

        return credentials
```

### Pattern 4: Credential Transformation

Transform credential values before use:

```python
class TransformingCredentialLoader(BaseCredentialLoader):
    """Loader that transforms credential values."""

    def load_credentials(self) -> dict[str, str]:
        """Load and transform credentials."""
        credentials = super().load_credentials()

        # Transform values
        for key, value in credentials.items():
            # Remove whitespace
            credentials[key] = value.strip()

            # Expand variables
            credentials[key] = os.path.expandvars(value)

            # Decode if needed
            if key.endswith("_BASE64"):
                import base64
                decoded_key = key.replace("_BASE64", "")
                credentials[decoded_key] = base64.b64decode(value).decode()
                del credentials[key]

        return credentials
```

## Integration with Secret Providers

The credential loader system integrates with the [secrets architecture](../architecture/secrets-architecture.md) via SecretProvider dependency injection.

### Using Custom Secret Provider

```python
from infrafoundry.core.credential_loader import CredentialLoader
from infrafoundry.core.secrets.providers.vault import VaultSecretProvider

# Use HashiCorp Vault instead of SOPS
vault_provider = VaultSecretProvider(
    vault_addr="https://vault.company.com",
    vault_token=os.getenv("VAULT_TOKEN")
)

# Inject into credential loader
loader = CredentialLoader(
    config_dir=Path("/path/to/config"),
    secret_provider=vault_provider
)

# Load credentials from Vault
credentials = loader.load("prod")
```

### Provider-Specific Secret Backends

Different providers can use different secret backends:

```python
class MultiBackendCredentialLoader(BaseCredentialLoader):
    """Use different secret providers per credential type."""

    def __init__(self, secrets_dir, debug_mode=False):
        # Don't use default SOPS provider
        super().__init__(secrets_dir, debug_mode, secret_provider=None)

        # Initialize multiple providers
        self.sops_provider = SopsSecretProvider()
        self.vault_provider = VaultSecretProvider(...)

    def load_credentials(self) -> dict[str, str]:
        """Load from appropriate provider."""
        # Production credentials from Vault
        if "prod" in str(self.secrets_dir):
            self.secret_provider = self.vault_provider
        # Dev credentials from SOPS
        else:
            self.secret_provider = self.sops_provider

        return super().load_credentials()
```

## Testing

### Mock Credential Loading

```python
# tests/unit/test_custom_loader.py
import pytest
from unittest.mock import Mock, patch
from pathlib import Path

from infrafoundry.core.credential_loader.custom_loader import CustomCredentialLoader


@pytest.fixture
def mock_secret_provider():
    """Mock secret provider."""
    provider = Mock()
    provider.load_secret.return_value = {
        "custom_api_url": "https://api.example.com",
        "custom_api_key": "test-key-123"
    }
    return provider


def test_load_credentials(mock_secret_provider):
    """Test credential loading."""
    loader = CustomCredentialLoader(
        secrets_dir=Path("/fake/secrets"),
        secret_provider=mock_secret_provider
    )

    credentials = loader.load_credentials()

    assert credentials == {
        "CUSTOM_API_URL": "https://api.example.com",
        "CUSTOM_API_KEY": "test-key-123"
    }


def test_missing_credentials(mock_secret_provider):
    """Test handling of missing credential file."""
    from infrafoundry.core.exceptions import SecretNotFoundError

    mock_secret_provider.load_secret.side_effect = SecretNotFoundError("Not found")

    loader = CustomCredentialLoader(
        secrets_dir=Path("/fake/secrets"),
        secret_provider=mock_secret_provider
    )

    # Should return empty dict, not raise
    credentials = loader.load_credentials()
    assert credentials == {}
```

### Integration Testing

```python
def test_credential_loader_integration(tmp_path):
    """Test with real encrypted files."""
    # Create test environment
    env_dir = tmp_path / "envs" / "test"
    env_dir.mkdir(parents=True)

    # Create age key
    subprocess.run(["age-keygen", "-o", env_dir / "age.key"])

    # Create and encrypt credentials
    creds_file = env_dir / "custom.yaml"
    creds_file.write_text("""
custom_api_url: https://api.test.com
custom_api_key: test-key-123
""")

    subprocess.run([
        "sops", "--encrypt", "--in-place",
        "--age", "age1...",  # Use generated key
        str(creds_file)
    ])

    # Test loading
    loader = CredentialLoader(config_dir=tmp_path)
    credentials = loader.load("test", providers=["custom"])

    assert "CUSTOM_API_URL" in credentials
    assert credentials["CUSTOM_API_URL"] == "https://api.test.com"
```

## Troubleshooting

### Debug Mode

Enable debug logging to see credential loading process:

```bash
export INFRAFOUNDRY_LOG_LEVEL=DEBUG
```

```python
# Loader will log:
# - Which files it's looking for
# - Which fields it's mapping
# - How many credentials loaded
```

### Common Issues

**Issue: Credentials not loaded**

Check:
1. File exists: `ls envs/dev/proxmox.yaml`
2. File is encrypted: `head envs/dev/proxmox.yaml` (should see `sops:`)
3. Age key exists: `ls envs/dev/age.key`
4. Loader is registered in `PROVIDER_LOADERS`

**Issue: Wrong environment variables**

Verify field mapping in your loader:
```python
print(loader.field_mapping)
# Should match your secret file keys → env var names
```

**Issue: Decryption fails**

Check age key permissions:
```bash
chmod 600 envs/dev/age.key
```

Verify SOPS configuration:
```bash
sops --decrypt envs/dev/proxmox.yaml
```

## Best Practices

### 1. Consistent Naming

Use consistent naming conventions for:
- Credential file names (`<provider>.yaml`)
- Secret keys (`<provider>_<field>`)
- Environment variables (`<PROVIDER>_<FIELD>`)

### 2. Required vs Optional Fields

Clearly document which fields are required:

```python
@property
def field_mapping(self) -> dict[str, str]:
    """Return credential mapping.

    Required fields:
    - api_url: API endpoint URL
    - api_key: API authentication key

    Optional fields:
    - api_secret: API secret (if using key+secret auth)
    - api_region: API region (defaults to us-east-1)
    """
    return {
        "api_url": "PROVIDER_API_URL",      # Required
        "api_key": "PROVIDER_API_KEY",       # Required
        "api_secret": "PROVIDER_API_SECRET", # Optional
        "api_region": "PROVIDER_API_REGION", # Optional
    }
```

### 3. Avoid Hardcoded Values

Never hardcode credentials:

```python
# Bad
def load_credentials(self):
    return {
        "API_KEY": "hardcoded-key-123"  # NEVER DO THIS
    }

# Good
def load_credentials(self):
    # Load from encrypted file
    return super().load_credentials()
```

### 4. Use Type Hints

Always use type hints for clarity:

```python
from typing import override

class CustomLoader(BaseCredentialLoader):
    @property
    @override
    def provider_name(self) -> str:
        return "custom"

    @property
    @override
    def credential_file(self) -> str:
        return "custom.yaml"

    @property
    @override
    def field_mapping(self) -> dict[str, str]:
        return {"key": "VALUE"}
```

## Examples

### Complete Example: Azure Loader

```python
# src/infrafoundry/core/credential_loader/azure_loader.py
from typing import override
from infrafoundry.core.credential_loader.base_loader import BaseCredentialLoader


class AzureCredentialLoader(BaseCredentialLoader):
    """Loads Azure-specific credentials.

    Credential file: azure.yaml
    Environment variables: AZURE_*

    Required fields:
    - azure_tenant_id: Azure AD tenant ID
    - azure_client_id: Service principal client ID
    - azure_client_secret: Service principal secret
    - azure_subscription_id: Azure subscription ID

    Optional fields:
    - azure_resource_group: Default resource group
    - azure_location: Default location
    """

    @property
    @override
    def provider_name(self) -> str:
        return "azure"

    @property
    @override
    def credential_file(self) -> str:
        return "azure.yaml"

    @property
    @override
    def field_mapping(self) -> dict[str, str]:
        return {
            # Required
            "azure_tenant_id": "AZURE_TENANT_ID",
            "azure_client_id": "AZURE_CLIENT_ID",
            "azure_client_secret": "AZURE_CLIENT_SECRET",
            "azure_subscription_id": "AZURE_SUBSCRIPTION_ID",
            # Optional
            "azure_resource_group": "AZURE_RESOURCE_GROUP",
            "azure_location": "AZURE_LOCATION",
        }
```

**Credential file:**
```yaml
# envs/prod/azure.yaml (encrypted)
azure_tenant_id: "12345678-1234-1234-1234-123456789012"
azure_client_id: "87654321-4321-4321-4321-210987654321"
azure_client_secret: "super-secret-value-here"
azure_subscription_id: "abcdef12-3456-7890-abcd-ef1234567890"
azure_resource_group: "infra-prod-rg"
azure_location: "eastus"
```

**Usage:**
```python
from infrafoundry.core.credential_loader import CredentialLoader

loader = CredentialLoader()
with loader.temporary_credentials("prod") as creds:
    from azure.identity import ClientSecretCredential
    from azure.mgmt.compute import ComputeManagementClient

    # Credentials loaded from environment
    credential = ClientSecretCredential(
        tenant_id=os.getenv("AZURE_TENANT_ID"),
        client_id=os.getenv("AZURE_CLIENT_ID"),
        client_secret=os.getenv("AZURE_CLIENT_SECRET")
    )

    compute_client = ComputeManagementClient(
        credential,
        os.getenv("AZURE_SUBSCRIPTION_ID")
    )
```

## References

- [Secrets Architecture](../architecture/secrets-architecture.md) - Pluggable secret backend system
- [Per-Environment Credentials](../per-environment-credentials.md) - User guide for managing credentials
- [BaseCredentialLoader Source](../../src/infrafoundry/core/credential_loader/base_loader.py)
- [CredentialLoader Source](../../src/infrafoundry/core/credential_loader/credential_loader.py)
