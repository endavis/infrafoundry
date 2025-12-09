# Vaultwarden / Bitwarden Secret Provider

InfraFoundry can integrate with Vaultwarden (or official Bitwarden) to manage secrets, offering an alternative to the file-based SOPS backend.

## Prerequisites

1.  **Bitwarden CLI (`bw`)**: Must be installed on the machine running InfraFoundry.
    *   Installation: [Bitwarden CLI Help](https://bitwarden.com/help/cli/)
2.  **Authentication**: The CLI must be logged in.
    *   Run `bw login` and `bw unlock` before running InfraFoundry.
    *   Alternatively, set `BW_SESSION` environment variable with the session key.

## Configuration

To use Vaultwarden as your secret provider, inject the `VaultwardenProvider` into the `SecretManager`.

### Programmatic Usage

```python
from infrafoundry.core.secrets import SecretManager
from infrafoundry.core.secrets.providers.vaultwarden import VaultwardenProvider
import os

# Ensure BW_SESSION is set or passed explicitly
session_key = os.getenv("BW_SESSION")

provider = VaultwardenProvider(session_key=session_key)
manager = SecretManager(env_name="dev", provider=provider)

# Load a secret
# Maps to a Bitwarden item named "my-secret-item"
secret = manager.decrypt_file("my-secret-item")
print(secret["username"])
print(secret["password"])
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
*   **"Bitwarden item not found"**: Ensure the item name matches exactly and the CLI is synced (`bw sync`).
*   **Authentication Errors**: Verify `BW_SESSION` is valid and the vault is unlocked.
