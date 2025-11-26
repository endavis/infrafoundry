"""Secret management using SOPS with age encryption."""

import json
from pathlib import Path
from typing import Any

import yaml

from infrafoundry.core.base_manager import PathBasedManager
from infrafoundry.core.secrets.age_key_manager import check_age_key, create_sops_config
from infrafoundry.core.secrets.sops_wrapper import (
    check_sops_installed,
    decrypt_file,
    encrypt_file,
)


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
            base_dir = Path(config_repo) if config_repo else Path.cwd()
            # Default to local ./envs/{env} when config repo env var is absent
            secrets_dir = base_dir / "envs" / env_name

        self.secrets_dir: Path = secrets_dir  # Type assertion - secrets_dir is always Path here
        self._log_debug(
            f"Initialized SecretManager for environment '{self.env_name}' "
            f"with secrets_dir: {self.secrets_dir}"
        )

        # Validate SOPS and age setup
        check_sops_installed()
        check_age_key()

    def decrypt_file(self, filename: str) -> dict[str, Any]:
        """Decrypt a SOPS-encrypted file.

        Args:
            filename: Name of encrypted file (e.g., 'proxmox.yaml')

        Returns:
            Decrypted data as dictionary
        """
        encrypted_file = self.secrets_dir / filename
        self._log_debug(f"Decrypting file: {filename}")
        data = decrypt_file(encrypted_file)
        self._log_debug(f"Successfully decrypted: {filename}")
        return data

    def encrypt_file(self, filename: str, data: dict[str, Any]) -> None:
        """Encrypt data and save to file.

        Args:
            filename: Name of file to create (e.g., 'proxmox.yaml')
            data: Data to encrypt
        """
        self._ensure_directory_exists(self.secrets_dir)
        encrypted_file = self.secrets_dir / filename
        self._log_debug(f"Encrypting file: {filename}")
        encrypt_file(encrypted_file, data)
        self._log_info(f"Successfully encrypted: {filename}")

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
        create_sops_config(self.secrets_dir, age_public_key)

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
