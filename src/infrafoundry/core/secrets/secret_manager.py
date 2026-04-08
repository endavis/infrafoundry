"""Secret management using SOPS with age encryption."""

import json
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from infrafoundry.core.base_manager import PathBasedManager
from infrafoundry.core.secrets.age_key_manager import check_age_key, create_sops_config
from infrafoundry.core.secrets.provider import SecretProvider
from infrafoundry.core.secrets.providers.sops import SopsSecretProvider
from infrafoundry.core.secrets.rotation import SecretsRotator
from infrafoundry.core.security.file_utils import secure_write, secure_write_yaml

if TYPE_CHECKING:
    from infrafoundry.core.config.models import EnvironmentConfig

#: Default filename for the per-environment encrypted secrets file.
DEFAULT_SECRETS_FILENAME = "secrets.yaml"


class SecretManager(PathBasedManager):
    """Manages encrypted secrets using SOPS and age.

    Uses per-environment secrets stored in secrets/{env}/ directories.
    """

    def __init__(
        self,
        env_name: str,
        secrets_dir: Path | None = None,
        provider: SecretProvider | None = None,
    ) -> None:
        """Initialize secret manager.

        Args:
            env_name: Environment name (e.g., 'dev', 'prod') - used to determine
                     environment directory (envs/{env}/)
            secrets_dir: Base directory containing environment folders
                (defaults to INFRAFOUNDRY_CONFIG_REPO/envs/{env})
            provider: Secret provider implementation (defaults to SopsSecretProvider)

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
        skip_sops_checks = self._get_env_var("INFRAFOUNDRY_SKIP_SOPS_CHECK")
        force_sops_checks = self._get_env_var("INFRAFOUNDRY_FORCE_SOPS_CHECK")
        should_check = bool(force_sops_checks) or not bool(skip_sops_checks)

        if not should_check:
            self._log_warning(
                "Skipping SOPS/age checks because INFRAFOUNDRY_SKIP_SOPS_CHECK is set. "
                "Use only in non-production environments."
            )

        if provider:
            self.provider = provider
        else:
            # Use SopsSecretProvider by default
            self.provider = SopsSecretProvider()

        if should_check and isinstance(self.provider, SopsSecretProvider):
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
        data = self.provider.load_secret(encrypted_file)
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
        self.provider.save_secret(encrypted_file, data)
        self._log_info(f"Successfully encrypted: {filename}")

    @staticmethod
    def flatten_dict(data: dict[str, Any] | None) -> dict[str, str]:
        """Recursively flatten a nested dict into dotted-key string entries.

        Used to convert a decrypted secrets tree (e.g.
        ``{"tailscale": {"oauth_client_secret": "abc"}}``) into a flat
        lookup table (``{"tailscale.oauth_client_secret": "abc"}``)
        suitable for resolving resource ``terraform_secrets:`` references.

        Rules:
        - Nested dicts are descended; their keys are joined with ``.``.
        - Empty dict nodes are skipped (they have no leaf to expose).
        - Non-dict, non-None leaves are stringified via ``str()``.
        - ``None`` leaves are skipped — a missing value is the same as
          "not set".
        - List/tuple leaves are stringified as JSON to preserve structure
          while still producing a single env var string.

        Args:
            data: The dict to flatten. ``None`` returns an empty dict.

        Returns:
            Flat dict mapping dotted keys to string values.
        """
        if not data:
            return {}

        result: dict[str, str] = {}

        def _walk(prefix: str, node: Any) -> None:
            if isinstance(node, dict):
                if not node:
                    return
                for key, value in node.items():
                    new_prefix = f"{prefix}.{key}" if prefix else str(key)
                    _walk(new_prefix, value)
                return
            if node is None:
                return
            if isinstance(node, str):
                result[prefix] = node
            elif isinstance(node, bool | int | float):
                result[prefix] = str(node)
            else:
                # list/tuple/other — stringify as JSON for stability
                result[prefix] = json.dumps(node)

        _walk("", data)
        return result

    def flatten(self) -> dict[str, str]:
        """Decrypt the env's default secrets file and return it flattened.

        Convenience wrapper for callers that want a one-shot flatten of the
        environment's primary secrets file (``envs/{env}/secrets.yaml``).
        Returns an empty dict if the file does not exist.

        Returns:
            Flat dict mapping dotted keys to string secret values.
        """
        secrets_file = self.secrets_dir / DEFAULT_SECRETS_FILENAME
        if not secrets_file.exists():
            return {}
        data = self.decrypt_file(DEFAULT_SECRETS_FILENAME)
        return self.flatten_dict(data)

    def populate_environment_config(self, env_config: "EnvironmentConfig") -> None:
        """Decrypt the env's secrets file and attach it to the env config.

        Reads ``envs/{env}/secrets.yaml`` (if present), decrypts it via the
        configured ``SecretProvider``, and assigns the resulting nested
        plaintext dict to ``env_config.secrets``. If no secrets file exists,
        the field is left as ``None``.

        This method is intentionally defensive: a missing secrets file is
        not an error, since not every environment has secrets.

        Args:
            env_config: The environment configuration to populate. Mutated
                in place.
        """
        secrets_file = self.secrets_dir / DEFAULT_SECRETS_FILENAME
        if not secrets_file.exists():
            self._log_debug(
                f"No secrets file found at {secrets_file}; "
                f"env '{self.env_name}' has no secrets to populate."
            )
            env_config.secrets = None
            return

        try:
            decrypted = self.decrypt_file(DEFAULT_SECRETS_FILENAME)
        except Exception as exc:
            self._log_error(f"Failed to decrypt secrets file for env '{self.env_name}': {exc}")
            raise

        env_config.secrets = decrypted
        self._log_debug(
            f"Populated env '{self.env_name}' with decrypted secrets "
            f"({len(self.flatten_dict(decrypted))} flat keys)."
        )

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
        lines: list[str] = []
        for key, value in data.items():
            if isinstance(value, str):
                lines.append(f'{key} = "{value}"\n')
            else:
                lines.append(f"{key} = {json.dumps(value)}\n")
        secure_write(output_file, "".join(lines))

    def export_for_ansible(self, filename: str, output_file: Path) -> None:
        """Export secrets as Ansible vars file.

        Args:
            filename: Name of encrypted secrets file
            output_file: Path to write vars file
        """
        data = self.decrypt_file(filename)
        secure_write_yaml(output_file, data)

    @contextmanager
    def temporary_export(
        self, filename: str, output_file: Path, fmt: str = "terraform"
    ) -> Generator[Path, None, None]:
        """Export secrets to a temporary file and clean up after use.

        Args:
            filename: Name of encrypted secrets file
            output_file: Path to write the exported file
            fmt: Export format - "terraform" for tfvars or "ansible" for YAML vars

        Yields:
            Path to the exported file

        Raises:
            ValueError: If fmt is not "terraform" or "ansible"
        """
        if fmt == "terraform":
            self.export_for_terraform(filename, output_file)
        elif fmt == "ansible":
            self.export_for_ansible(filename, output_file)
        else:
            raise ValueError(f"Unsupported export format: {fmt}")

        try:
            yield output_file
        finally:
            self.cleanup_secret_files(output_file)

    @staticmethod
    def cleanup_secret_files(*paths: Path) -> None:
        """Remove exported secret files from disk.

        Args:
            paths: Paths to secret files to remove
        """
        for path in paths:
            path.unlink(missing_ok=True)

    def cleanup(self) -> None:
        """Cleanup resources (required by BaseManager).

        No cleanup needed for SecretManager as it doesn't maintain
        persistent connections or file handles.
        """
        self._log_debug("SecretManager cleanup complete")

    def rotate_secrets(
        self,
        new_key_file: Path | None = None,
        generate_new_key: bool = False,
        file_patterns: list[str] | None = None,
        verify: bool = True,
        keep_backup: bool = True,
    ) -> dict[str, Any]:
        """Rotate secrets with a new age encryption key.

        This re-encrypts all secrets with a new age key, providing safe key rotation
        with automatic backup and rollback capabilities.

        Args:
            new_key_file: Path to new age key file (required if generate_new_key=False)
            generate_new_key: Generate a new age key automatically
            file_patterns: Optional file patterns to rotate (default: all .yaml files)
            verify: Verify re-encryption was successful (default: True)
            keep_backup: Keep backup after successful rotation (default: True)

        Returns:
            Dictionary with rotation results:
                - success: bool
                - files_rotated: list[str]
                - new_public_key: str
                - backup_path: str
                - errors: list[str] (if any)

        Raises:
            SecretError: If rotation fails

        Example:
            # Generate new key and rotate all secrets
            manager = SecretManager(env_name="dev")
            result = manager.rotate_secrets(generate_new_key=True)

            # Rotate with existing new key
            result = manager.rotate_secrets(new_key_file=Path("new_age.key"))
        """
        rotator = SecretsRotator(
            secrets_dir=self.secrets_dir,
            provider=self.provider,
        )

        return rotator.rotate(
            new_key_file=new_key_file,
            generate_new_key=generate_new_key,
            file_patterns=file_patterns,
            verify=verify,
            keep_backup=keep_backup,
        )
