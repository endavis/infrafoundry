from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class SecretProvider(ABC):
    """
    Abstract base class for secret providers.
    Defines the interface for loading and saving secrets.
    """

    @abstractmethod
    def load_secret(self, location: str | Path) -> dict[str, Any]:
        """
        Loads a secret from a specified location.

        Args:
            location: The location of the secret.
                      For SOPS, this is a file path.
                      For Vault, this might be a secret path (e.g., "secret/data/myapp").

        Returns:
            The secret data as a dictionary.

        Raises:
            SecretError: If the secret cannot be loaded.
        """
        pass

    @abstractmethod
    def save_secret(self, location: str | Path, data: dict[str, Any]) -> None:
        """
        Saves a secret to a specified location.

        Args:
            location: The location to save the secret.
            data: The data to save.

        Raises:
            SecretError: If the secret cannot be saved.
        """
        pass
