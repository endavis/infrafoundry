"""Secret management using SOPS with age encryption."""

import json
import subprocess
from pathlib import Path
from typing import Any

import yaml

from infrafoundry.core.base_manager import PathBasedManager


class SecretManager(PathBasedManager):
    """Manages encrypted secrets using SOPS and age.

    Uses per-environment secrets stored in secrets/{env}/ directories.
    """

    def __init__(self, env_name: str, secrets_dir: Path | None = None) -> None:
        """Initialize secret manager.

        Args:
            env_name: Environment name (e.g., 'dev', 'prod') - used to determine
                     environment directory (envs/{env}/)
            secrets_dir: Base directory containing environment folders
                (defaults to INFRAFOUNDRY_CONFIG_REPO/envs/{env})

        Raises:
            ValueError: If secrets_dir is None and INFRAFOUNDRY_CONFIG_REPO is not set
        """
        # Initialize base manager with logging
        super().__init__()

        self.env_name = env_name

        # Resolve secrets directory using PathBasedManager pattern
        if secrets_dir is None:
            config_repo = self._get_env_var("INFRAFOUNDRY_CONFIG_REPO")
            if not config_repo:
                raise ValueError(
                    "INFRAFOUNDRY_CONFIG_REPO environment variable must be set. "
                    "Please point it to your configuration repository. "
                    "See docs/separate-config-repo.md for setup instructions."
                )
            # Config repo is specified - use environment directory (envs/{env}/)
            # This is where settings.yaml and age.key live together
            secrets_dir = Path(config_repo) / "envs" / env_name

        self.secrets_dir: Path = secrets_dir  # Type assertion - secrets_dir is always Path here
        self._log_debug(
            f"Initialized SecretManager for environment '{env_name}' "
            f"with secrets_dir: {self.secrets_dir}"
        )

        # Validate SOPS and age setup
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
            self._log_debug("SOPS is installed and available")
        except (subprocess.CalledProcessError, FileNotFoundError):
            error_msg = "sops not found. Install with: brew install sops (macOS) or see https://github.com/getsops/sops"
            self._log_error(error_msg)
            raise RuntimeError(error_msg)

    def _check_age_key(self) -> None:
        """Check if age key is configured."""
        age_key_file = self._get_env_var("SOPS_AGE_KEY_FILE")
        if not age_key_file:
            error_msg = (
                f"SOPS_AGE_KEY_FILE not set. Generate a key with: "
                f"age-keygen -o envs/{self.env_name}/age.key"
            )
            self._log_error(error_msg)
            raise ValueError(error_msg)

        age_key_path = Path(age_key_file)
        if not age_key_path.exists():
            error_msg = f"Age key file not found: {age_key_file}"
            self._log_error(error_msg)
            raise FileNotFoundError(error_msg)

        self._log_debug(f"Age key file found: {age_key_file}")

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
            error_msg = f"Encrypted file not found: {encrypted_file}"
            self._log_error(error_msg)
            raise FileNotFoundError(error_msg)

        self._log_debug(f"Decrypting file: {filename}")
        try:
            result = subprocess.run(
                ["sops", "--decrypt", str(encrypted_file)],
                capture_output=True,
                check=True,
                text=True,
            )
            self._log_debug(f"Successfully decrypted: {filename}")
            return yaml.safe_load(result.stdout)
        except subprocess.CalledProcessError as e:
            error_msg = f"Failed to decrypt {filename}: {e.stderr}"
            self._log_error(error_msg)
            raise RuntimeError(error_msg)

    def encrypt_file(self, filename: str, data: dict[str, Any]) -> None:
        """Encrypt data and save to file.

        Args:
            filename: Name of file to create (e.g., 'proxmox.yaml')
            data: Data to encrypt

        Raises:
            RuntimeError: If encryption fails
        """
        self._ensure_directory_exists(self.secrets_dir)
        encrypted_file = self.secrets_dir / filename

        # Write unencrypted data to temp file
        temp_file = encrypted_file.with_suffix(".tmp")
        self._log_debug(f"Writing temp file: {temp_file}")
        with open(temp_file, "w") as f:
            yaml.dump(data, f)

        try:
            # Encrypt in place
            self._log_debug(f"Encrypting file: {filename}")
            subprocess.run(
                ["sops", "--encrypt", "--in-place", str(temp_file)],
                capture_output=True,
                check=True,
            )
            # Move to final location
            temp_file.rename(encrypted_file)
            self._log_info(f"Successfully encrypted: {filename}")
        except subprocess.CalledProcessError as e:
            temp_file.unlink(missing_ok=True)
            error_msg = f"Failed to encrypt {filename}: {e.stderr}"
            self._log_error(error_msg)
            raise RuntimeError(error_msg)

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

    def cleanup(self) -> None:
        """Cleanup resources (required by BaseManager).

        No cleanup needed for SecretManager as it doesn't maintain
        persistent connections or file handles.
        """
        self._log_debug("SecretManager cleanup complete")
