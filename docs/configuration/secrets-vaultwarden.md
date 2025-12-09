# Vaultwarden / Bitwarden Secret Provider

InfraFoundry can integrate with Vaultwarden (or official Bitwarden) to manage secrets, offering an alternative to the file-based SOPS backend.

## Prerequisites

1.  **Bitwarden CLI (`bw`)**: Must be installed on the machine running InfraFoundry.
    *   Installation: [Bitwarden CLI Help](https://bitwarden.com/help/cli/)

## Authentication (CI/CD Friendly)

The provider supports multiple ways to authenticate, making it suitable for both local development and CI/CD pipelines.

### Option 1: Manual Session (Local Dev)
If you have already logged in via `bw login` and unlocked via `bw unlock`, you can simply set the session key:
```bash
export BW_SESSION="your-session-key"
```

### Option 2: Auto-Login (CI/CD)
The provider can automatically log in and unlock the vault if the following environment variables are present:

*   `BW_CLIENTID`: API Client ID (from web vault settings)
*   `BW_CLIENTSECRET`: API Client Secret
*   `BW_PASSWORD`: Master Password (required to decrypt secrets)
*   *(Optional)* `BW_SERVER`: If using a self-hosted instance (Vaultwarden), set this to your server URL.

**Security Note:** Providing the Master Password in CI variables (`BW_PASSWORD`) is necessary because the standard `bw` CLI requires it to generate the keys for decryption. Ensure this variable is masked/protected in your CI system.

## Configuration

To use Vaultwarden as your secret provider, inject the `VaultwardenProvider` into the `SecretManager`.

### Programmatic Usage

```python
from infrafoundry.core.secrets import SecretManager
from infrafoundry.core.secrets.providers.vaultwarden import VaultwardenProvider
import os

# Session key is auto-detected from env or auto-negotiated via credentials
provider = VaultwardenProvider()
manager = SecretManager(env_name="dev", provider=provider)

# Load a secret
secret = manager.decrypt_file("my-secret-item")
print(secret["username"])
```

### Data Mapping

The provider maps Bitwarden item fields to a flat dictionary:

*   **Login Item:**
    *   `login.username` -> `username`
    *   `login.password` -> `password`
*   **Fields:**
    *   Custom fields are mapped by their `name` to keys in the dictionary.
*   **Notes:**
    *   The `notes` field is mapped to the `notes` key.

## Saving Secrets

When saving secrets via `manager.encrypt_file("item-name", data)`:

1.  Standard keys `username` and `password` are stored in the item's login section.
2.  `notes` is stored in the notes section.
3.  All other keys are stored as custom fields (type: Text).
4.  If the item exists, it is updated. If not, it is created.

## Troubleshooting

*   **"Bitwarden CLI (bw) not found"**: Ensure `bw` is in your system PATH.
*   **"Vault is locked and BW_PASSWORD is not set"**: You are in a CI environment (or have no session) and haven't provided the password to unlock.
*   **"Bitwarden item not found"**: Ensure the item name matches exactly and the CLI is synced (`bw sync`).