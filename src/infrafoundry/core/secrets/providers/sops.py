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

    @staticmethod
    def _is_sops_encrypted(file_content: str) -> bool:
        """Check whether file content contains SOPS encryption markers.

        Both the ``sops:`` metadata key and ``ENC[AES256_GCM,`` value markers
        must be present for the file to be considered SOPS-encrypted.

        Args:
            file_content: Raw file content to inspect.

        Returns:
            True if the content appears to be SOPS-encrypted.
        """
        return "sops:" in file_content and "ENC[AES256_GCM," in file_content

    def load_secret(self, location: str | Path) -> dict[str, Any]:
        """Load a secret from a file, decrypting with SOPS only if encrypted.

        Reads the file content and checks for SOPS encryption markers.
        Plaintext YAML files are loaded directly without requiring sops
        to be installed.  Encrypted files are decrypted via ``sops --decrypt``.

        Args:
            location: Path to the secret file.

        Returns:
            The secret data as a dictionary.
        """
        file_path = Path(location)
        if not file_path.exists():
            raise SecretNotFoundError(f"Secret file not found: {file_path}")

        try:
            raw = file_path.read_text()
        except Exception as e:
            raise SecretError(f"Failed to read secret file {file_path}: {e}") from e

        # Plaintext YAML — return directly without requiring sops
        if not self._is_sops_encrypted(raw):
            try:
                return cast(dict[str, Any], yaml.safe_load(raw)) or {}
            except yaml.YAMLError as e:
                raise SecretDecryptionError(f"Failed to parse YAML from {file_path}: {e}") from e

        # Encrypted — sops must be available
        self._ensure_sops_installed()
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
