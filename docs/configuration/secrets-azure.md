# Azure Key Vault Provider

InfraFoundry can integrate with Azure Key Vault to manage secrets.

## Prerequisites

1.  **Azure Key Vault**: A Key Vault must be provisioned in Azure.
2.  **Authentication**: The environment must be authenticated using `DefaultAzureCredential`, which supports:
    *   Environment variables (`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_CLIENT_SECRET`)
    *   Managed Identity (if running in Azure)
    *   Azure CLI (`az login`)
3.  **Permissions**: The identity must have permissions to Get and Set secrets in the vault (Access Policies or RBAC).

## Configuration

Inject the `AzureKeyVaultProvider` into the `SecretManager`.

### Programmatic Usage

```python
from infrafoundry.core.secrets import SecretManager
from infrafoundry.core.secrets.providers.azure import AzureKeyVaultProvider

# Initialize provider with your Vault URL
vault_url = "https://my-infra-vault.vault.azure.net/"
provider = AzureKeyVaultProvider(vault_url=vault_url)

manager = SecretManager(env_name="dev", provider=provider)

# Load a secret
# Maps to an Azure Secret named "db-password"
secret = manager.decrypt_file("db-password")
print(secret["value"])
```

### Data Mapping

*   **JSON Secrets**: Secrets stored as JSON strings are parsed and returned as a dictionary.
*   **Plain String Secrets**: If a secret is a plain string, it is returned as `{"value": "the-secret-string"}`.

## Saving Secrets

When saving secrets:
1.  The dictionary data is converted to a JSON string.
2.  `set_secret` is called to create or update the secret.

## Troubleshooting

*   **"ResourceNotFoundError"**: The secret name does not exist in the vault.
*   **Auth Errors**: Ensure `az login` has been run or environment variables are set correctly.
