import logging
import shutil
import subprocess  # nosec B404 - required for running sops
from pathlib import Path
from typing import Any, cast

import yaml

from infrafoundry.core.exceptions import (
    SecretDecryptionError,
    SecretError,
    SecretNotFoundError,
)
from infrafoundry.core.secrets.provider import SecretProvider
from infrafoundry.core.security.file_utils import secure_write_yaml

logger = logging.getLogger(__name__)


class SopsSecretProvider(SecretProvider):
    """
    Secret provider implementation using Mozilla SOPS.
    """

    @property
    def _sops_path(self) -> str:
        """Return the full path to the sops executable."""
        path = shutil.which("sops")
        if path is None:
            error_msg = (
                "sops not found. Install with: brew install sops (macOS) "
                "or see https://github.com/getsops/sops"
            )
            raise SecretError(error_msg)
        return path

    def _ensure_sops_installed(self) -> None:
        """Check if sops is installed."""
        _ = self._sops_path  # Will raise SecretError if not found

    def load_secret(self, location: str | Path) -> dict[str, Any]:
        """
        Loads a secret from a file using SOPS.

        Args:
            location: Path to the encrypted file.

        Returns:
            The decrypted data as a dictionary.
        """
        self._ensure_sops_installed()
        file_path = Path(location)
        if not file_path.exists():
            raise SecretNotFoundError(f"Encrypted file not found: {file_path}")

        try:
            result = subprocess.run(  # nosec B603
                [self._sops_path, "--decrypt", str(file_path)],
                capture_output=True,
                check=True,
                text=True,
            )
            return cast(dict[str, Any], yaml.safe_load(result.stdout)) or {}
        except subprocess.CalledProcessError as e:
            raise SecretDecryptionError(f"Failed to decrypt {file_path}: {e.stderr}") from e
        except yaml.YAMLError as e:
            raise SecretDecryptionError(
                f"Failed to parse decrypted YAML from {file_path}: {e}"
            ) from e
        except Exception as e:
            raise SecretError(f"Unexpected error loading secret from {file_path}: {e}") from e

    def save_secret(self, location: str | Path, data: dict[str, Any]) -> None:
        """
        Saves a secret to a file using SOPS.

        Args:
            location: Path where the encrypted file should be saved.
            data: Data to encrypt and save.
        """
        self._ensure_sops_installed()
        file_path = Path(location)

        # Logic adapted from sops_wrapper.py
        # Write unencrypted data to temp file
        # Use tempfile to be safe

        # We need to write to a temp file in the same directory or system temp.
        # sops_wrapper used .tmp suffix in the same dir.

        temp_file = file_path.with_suffix(".tmp")

        try:
            secure_write_yaml(temp_file, data)

            # Encrypt in place
            subprocess.run(  # nosec B603
                [self._sops_path, "--encrypt", "--in-place", str(temp_file)],
                capture_output=True,
                check=True,
            )

            # Move to final location
            temp_file.rename(file_path)

        except subprocess.CalledProcessError as e:
            temp_file.unlink(missing_ok=True)
            raise SecretError(f"Failed to encrypt {file_path}: {e.stderr}") from e
        except Exception as e:
            temp_file.unlink(missing_ok=True)
            raise SecretError(f"Failed to save secret to {file_path}: {e}") from e

    def create_sops_config(self, directory: Path, age_public_key: str) -> None:
        """
        Create .sops.yaml configuration file.
        This is specific to SOPS but useful to have here.
        """
        config_path = directory / ".sops.yaml"
        if config_path.exists():
            return

        config = {
            "creation_rules": [
                {
                    "path_regex": ".*",
                    "age": age_public_key,
                }
            ]
        }

        try:
            with open(config_path, "w") as f:
                yaml.dump(config, f)
        except Exception as e:
            raise SecretError(f"Failed to create .sops.yaml at {directory}: {e}") from e
