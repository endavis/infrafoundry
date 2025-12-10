import json
import logging
from pathlib import Path
from typing import Any, cast

from azure.core.exceptions import ResourceNotFoundError
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

from infrafoundry.core.exceptions import SecretError, SecretNotFoundError
from infrafoundry.core.secrets.provider import SecretProvider

logger = logging.getLogger(__name__)


class AzureKeyVaultProvider(SecretProvider):
    """
    Secret provider implementation using Azure Key Vault.
    """

    def __init__(self, vault_url: str) -> None:
        """
        Initialize Azure Key Vault provider.

        Args:
            vault_url: URL of the Key Vault (e.g., https://my-vault.vault.azure.net/).
        """
        self.vault_url = vault_url
        try:
            credential = DefaultAzureCredential()
            self.client = SecretClient(vault_url=vault_url, credential=credential)
        except Exception as e:
            raise SecretError(f"Failed to create Azure Key Vault client: {e}") from e

    def load_secret(self, location: str | Path) -> dict[str, Any]:
        """
        Load a secret from Azure Key Vault.

        Args:
            location: The name of the secret.

        Returns:
            Dictionary containing secret data.
        """
        secret_name = str(location)
        try:
            secret = self.client.get_secret(secret_name)
            value = secret.value
            if not value:
                return {}

            try:
                return cast(dict[str, Any], json.loads(value))
            except json.JSONDecodeError:
                return {"value": value}

        except ResourceNotFoundError as e:
            raise SecretNotFoundError(f"Azure Secret not found: {secret_name}") from e
        except Exception as e:
            raise SecretError(f"Failed to load Azure secret {secret_name}: {e}") from e

    def save_secret(self, location: str | Path, data: dict[str, Any]) -> None:
        """
        Save a secret to Azure Key Vault.

        Args:
            location: The name of the secret.
            data: Dictionary of data to save.
        """
        secret_name = str(location)
        secret_value = json.dumps(data)

        try:
            self.client.set_secret(secret_name, secret_value)
        except Exception as e:
            raise SecretError(f"Failed to save Azure secret {secret_name}: {e}") from e
