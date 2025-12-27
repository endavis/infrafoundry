"""Secrets rotation utilities for re-encrypting secrets with new keys."""

import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from infrafoundry.core.exceptions import SecretError
from infrafoundry.core.secrets.provider import SecretProvider
from infrafoundry.core.secrets.providers.sops import SopsSecretProvider


class SecretsRotator:
    """Handles rotation of encrypted secrets with new age keys.

    Provides safe key rotation with:
    - Automatic backup before rotation
    - Transaction-like semantics (all-or-nothing)
    - Verification after re-encryption
    - Rollback capability on failure
    """

    def __init__(
        self,
        secrets_dir: Path,
        provider: SecretProvider | None = None,
        backup_dir: Path | None = None,
    ) -> None:
        """Initialize secrets rotator.

        Args:
            secrets_dir: Directory containing encrypted secret files
            provider: Secret provider (defaults to SopsSecretProvider)
            backup_dir: Directory for backups (defaults to secrets_dir/../.secrets_backups)
        """
        self.secrets_dir = secrets_dir
        self.provider = provider or SopsSecretProvider()
        self.backup_dir = backup_dir or secrets_dir.parent / ".secrets_backups"
        self.current_backup: Path | None = None

    def generate_age_key(self, key_file: Path) -> str:
        """Generate a new age key pair.

        Args:
            key_file: Path where private key will be saved

        Returns:
            Age public key

        Raises:
            SecretError: If key generation fails
        """
        if key_file.exists():
            raise SecretError(f"Key file already exists: {key_file}")

        key_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            result = subprocess.run(
                ["age-keygen", "-o", str(key_file)],
                capture_output=True,
                text=True,
                check=True,
            )

            # Extract public key from stderr output
            for line in result.stderr.split("\n"):
                if line.startswith("# public key:"):
                    return line.split(": ")[1].strip()

            raise SecretError("Failed to extract age public key from age-keygen output")

        except subprocess.CalledProcessError as e:
            raise SecretError(f"Failed to generate age key: {e.stderr}") from e
        except FileNotFoundError:
            raise SecretError(
                "age-keygen not found. Install with: brew install age (macOS) "
                "or see https://github.com/FiloSottile/age"
            ) from None

    def create_backup(self) -> Path:
        """Create timestamped backup of encrypted files.

        Returns:
            Path to backup directory
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.backup_dir / f"backup_{timestamp}"
        backup_path.mkdir(parents=True, exist_ok=True)

        # Copy all encrypted YAML files
        encrypted_files = list(self.secrets_dir.glob("*.yaml"))
        if self.secrets_dir.joinpath(".sops.yaml").exists():
            encrypted_files.append(self.secrets_dir / ".sops.yaml")

        for file_path in encrypted_files:
            shutil.copy2(file_path, backup_path / file_path.name)

        self.current_backup = backup_path
        return backup_path

    def restore_backup(self, backup_path: Path) -> None:
        """Restore files from backup.

        Args:
            backup_path: Path to backup directory
        """
        if not backup_path.exists():
            raise SecretError(f"Backup directory not found: {backup_path}")

        # Restore all files from backup
        for backup_file in backup_path.glob("*.yaml"):
            target_file = self.secrets_dir / backup_file.name
            shutil.copy2(backup_file, target_file)

    def update_sops_config(self, new_public_key: str) -> None:
        """Update .sops.yaml with new age public key.

        Args:
            new_public_key: New age public key
        """
        sops_config_path = self.secrets_dir / ".sops.yaml"

        config = {
            "creation_rules": [
                {
                    "path_regex": r".*\.yaml$",
                    "age": new_public_key,
                }
            ]
        }

        with open(sops_config_path, "w") as f:
            yaml.dump(config, f)

    def get_encrypted_files(self, file_patterns: list[str] | None = None) -> list[Path]:
        """Get list of encrypted files to rotate.

        Args:
            file_patterns: Optional list of file patterns to filter
                          (e.g., ["*.yaml", "secrets.yaml"])
                          If None, rotates all .yaml files

        Returns:
            List of encrypted file paths
        """
        if file_patterns:
            files: list[Path] = []
            for pattern in file_patterns:
                files.extend(self.secrets_dir.glob(pattern))
            # Remove duplicates and .sops.yaml
            return [f for f in set(files) if f.name != ".sops.yaml"]
        else:
            # All .yaml files except .sops.yaml
            return [f for f in self.secrets_dir.glob("*.yaml") if f.name != ".sops.yaml"]

    def rotate(
        self,
        new_key_file: Path | None = None,
        generate_new_key: bool = False,
        file_patterns: list[str] | None = None,
        verify: bool = True,
        keep_backup: bool = True,
    ) -> dict[str, Any]:
        """Rotate secrets with a new age key.

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
        """
        if not generate_new_key and not new_key_file:
            raise SecretError("Must specify either new_key_file or generate_new_key=True")

        if generate_new_key and new_key_file:
            raise SecretError("Cannot specify both new_key_file and generate_new_key=True")

        results: dict[str, Any] = {
            "success": False,
            "files_rotated": [],
            "new_public_key": "",
            "backup_path": "",
            "errors": [],
        }

        try:
            # Step 1: Create backup
            backup_path = self.create_backup()
            results["backup_path"] = str(backup_path)

            # Step 2: Generate or use new key
            if generate_new_key:
                # Generate new key in secrets_dir
                new_key_path = self.secrets_dir / "age.key.new"
                new_public_key = self.generate_age_key(new_key_path)
                new_key_file = new_key_path
            else:
                # Extract public key from provided key file
                assert new_key_file is not None  # For type checker
                if not new_key_file.exists():
                    raise SecretError(f"New key file not found: {new_key_file}")
                new_public_key = self._extract_public_key(new_key_file)

            results["new_public_key"] = new_public_key

            # Step 3: Get files to rotate
            encrypted_files = self.get_encrypted_files(file_patterns)
            if not encrypted_files:
                results["errors"].append("No encrypted files found to rotate")
                return results

            # Step 4: Decrypt all files with old key
            decrypted_data: dict[Path, dict[str, Any]] = {}
            for file_path in encrypted_files:
                try:
                    data = self.provider.load_secret(file_path)
                    decrypted_data[file_path] = data
                except Exception as e:
                    raise SecretError(
                        f"Failed to decrypt {file_path.name} with old key: {e}"
                    ) from e

            # Step 5: Update .sops.yaml with new public key
            self.update_sops_config(new_public_key)

            # Step 6: Re-encrypt all files with new key by updating SOPS_AGE_KEY_FILE
            # We need to temporarily set SOPS_AGE_KEY_FILE to the new key
            import os

            old_key_file = os.environ.get("SOPS_AGE_KEY_FILE")
            try:
                os.environ["SOPS_AGE_KEY_FILE"] = str(new_key_file)

                for file_path, data in decrypted_data.items():
                    try:
                        self.provider.save_secret(file_path, data)
                        results["files_rotated"].append(str(file_path.name))
                    except Exception as e:
                        raise SecretError(
                            f"Failed to re-encrypt {file_path.name} with new key: {e}"
                        ) from e

                # Step 7: Verify if requested
                if verify:
                    self._verify_rotation(encrypted_files, decrypted_data)

            finally:
                # Restore old key file env var
                if old_key_file:
                    os.environ["SOPS_AGE_KEY_FILE"] = old_key_file
                elif "SOPS_AGE_KEY_FILE" in os.environ:
                    del os.environ["SOPS_AGE_KEY_FILE"]

            # Step 8: Success - optionally remove backup
            results["success"] = True
            if not keep_backup and backup_path.exists():
                shutil.rmtree(backup_path)
                results["backup_path"] = ""

            return results

        except Exception as e:
            # Rollback on failure
            if self.current_backup:
                try:
                    self.restore_backup(self.current_backup)
                    results["errors"].append(f"Rotation failed, restored backup: {e}")
                except Exception as restore_error:
                    results["errors"].append(
                        f"Rotation failed AND backup restore failed: {e}, {restore_error}"
                    )
            else:
                results["errors"].append(f"Rotation failed: {e}")

            raise SecretError(f"Secrets rotation failed: {e}") from e

    def _extract_public_key(self, key_file: Path) -> str:
        """Extract age public key from private key file.

        Args:
            key_file: Path to age private key

        Returns:
            Age public key
        """
        try:
            result = subprocess.run(
                ["age-keygen", "-y", str(key_file)],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            raise SecretError(f"Failed to extract public key: {e.stderr}") from e

    def _verify_rotation(
        self,
        encrypted_files: list[Path],
        original_data: dict[Path, dict[str, Any]],
    ) -> None:
        """Verify that re-encrypted files can be decrypted and match original data.

        Args:
            encrypted_files: List of re-encrypted files
            original_data: Original decrypted data for comparison

        Raises:
            SecretError: If verification fails
        """
        for file_path in encrypted_files:
            try:
                decrypted = self.provider.load_secret(file_path)
                original = original_data.get(file_path, {})

                if decrypted != original:
                    raise SecretError(
                        f"Verification failed for {file_path.name}: "
                        "re-encrypted data doesn't match original"
                    )
            except Exception as e:
                raise SecretError(f"Verification failed for {file_path.name}: {e}") from e
