"""Secret management using SOPS with age encryption."""

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import yaml


class SecretManager:
    """Manages encrypted secrets using SOPS and age."""

    def __init__(self, secrets_dir: Path | None = None) -> None:
        """Initialize secret manager.

        Args:
            secrets_dir: Directory containing encrypted secrets
                (defaults to INFRAFOUNDRY_CONFIG_REPO/secrets or ./secrets)
        """
        if secrets_dir is None:
            # Check for separate config repo first
            config_repo = os.getenv("INFRAFOUNDRY_CONFIG_REPO")
            if config_repo:
                secrets_dir = Path(config_repo) / "secrets"
            else:
                # Fall back to local secrets directory
                secrets_path = os.getenv("INFRAFOUNDRY_SECRETS_DIR", "secrets")
                secrets_dir = Path.cwd() / secrets_path
        self.secrets_dir = secrets_dir
        self._check_sops_installed()
        self._check_age_key()

    def _check_sops_installed(self) -> None:
        """Check if sops is installed."""
        try:
            subprocess.run(
                ["sops", "--version"],
                capture_output=True,
                check=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError(
                "sops not found. Install with: brew install sops (macOS) or see https://github.com/getsops/sops"
            )

    def _check_age_key(self) -> None:
        """Check if age key is configured."""
        age_key_file = os.getenv("SOPS_AGE_KEY_FILE")
        if not age_key_file:
            raise ValueError(
                "SOPS_AGE_KEY_FILE not set. Generate a key with: age-keygen -o secrets/age.key"
            )

        if not Path(age_key_file).exists():
            raise FileNotFoundError(f"Age key file not found: {age_key_file}")

    def decrypt_file(self, filename: str) -> dict[str, Any]:
        """Decrypt a SOPS-encrypted file.

        Args:
            filename: Name of encrypted file (e.g., 'proxmox.yaml')

        Returns:
            Decrypted data as dictionary

        Raises:
            FileNotFoundError: If encrypted file doesn't exist
            RuntimeError: If decryption fails
        """
        encrypted_file = self.secrets_dir / filename
        if not encrypted_file.exists():
            raise FileNotFoundError(f"Encrypted file not found: {encrypted_file}")

        try:
            result = subprocess.run(
                ["sops", "--decrypt", str(encrypted_file)],
                capture_output=True,
                check=True,
                text=True,
            )
            return yaml.safe_load(result.stdout)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to decrypt {filename}: {e.stderr}")

    def encrypt_file(self, filename: str, data: dict[str, Any]) -> None:
        """Encrypt data and save to file.

        Args:
            filename: Name of file to create (e.g., 'proxmox.yaml')
            data: Data to encrypt

        Raises:
            RuntimeError: If encryption fails
        """
        self.secrets_dir.mkdir(parents=True, exist_ok=True)
        encrypted_file = self.secrets_dir / filename

        # Write unencrypted data to temp file
        temp_file = encrypted_file.with_suffix(".tmp")
        with open(temp_file, "w") as f:
            yaml.dump(data, f)

        try:
            # Encrypt in place
            subprocess.run(
                ["sops", "--encrypt", "--in-place", str(temp_file)],
                capture_output=True,
                check=True,
            )
            # Move to final location
            temp_file.rename(encrypted_file)
        except subprocess.CalledProcessError as e:
            temp_file.unlink(missing_ok=True)
            raise RuntimeError(f"Failed to encrypt {filename}: {e.stderr}")

    def get_secret(self, filename: str, key: str) -> Any:
        """Get a specific secret value from an encrypted file.

        Args:
            filename: Name of encrypted file
            key: Key path using dot notation (e.g., 'api.token')

        Returns:
            Secret value

        Raises:
            KeyError: If key not found in decrypted data
        """
        data = self.decrypt_file(filename)
        keys = key.split(".")
        value = data
        for k in keys:
            value = value[k]
        return value

    def create_sops_config(self, age_public_key: str) -> None:
        """Create .sops.yaml configuration file.

        Args:
            age_public_key: Age public key for encryption
        """
        sops_config = {
            "creation_rules": [
                {
                    "path_regex": r".*\.yaml$",
                    "age": age_public_key,
                }
            ]
        }

        config_file = self.secrets_dir / ".sops.yaml"
        with open(config_file, "w") as f:
            yaml.dump(sops_config, f)

    def export_for_terraform(self, filename: str, output_file: Path) -> None:
        """Export secrets as Terraform variables file.

        Args:
            filename: Name of encrypted secrets file
            output_file: Path to write tfvars file
        """
        data = self.decrypt_file(filename)
        with open(output_file, "w") as f:
            for key, value in data.items():
                if isinstance(value, str):
                    f.write(f'{key} = "{value}"\n')
                else:
                    f.write(f"{key} = {json.dumps(value)}\n")

    def export_for_ansible(self, filename: str, output_file: Path) -> None:
        """Export secrets as Ansible vars file.

        Args:
            filename: Name of encrypted secrets file
            output_file: Path to write vars file
        """
        data = self.decrypt_file(filename)
        with open(output_file, "w") as f:
            yaml.dump(data, f)
