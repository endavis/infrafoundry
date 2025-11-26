"""Wrapper for SOPS command-line tool."""

import subprocess
from pathlib import Path
from typing import Any, cast

import yaml


def check_sops_installed() -> None:
    """Check if sops is installed."""
    try:
        subprocess.run(
            ["sops", "--version"],
            capture_output=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        error_msg = "sops not found. Install with: brew install sops (macOS) or see https://github.com/getsops/sops"
        raise RuntimeError(error_msg)


def decrypt_file(encrypted_file: Path) -> dict[str, Any]:
    """Decrypt a SOPS-encrypted file.

    Args:
        encrypted_file: Path to the encrypted file.

    Returns:
        Decrypted data as dictionary

    Raises:
        FileNotFoundError: If encrypted file doesn't exist
        RuntimeError: If decryption fails
    """
    if not encrypted_file.exists():
        raise FileNotFoundError(f"Encrypted file not found: {encrypted_file}")

    try:
        result = subprocess.run(
            ["sops", "--decrypt", str(encrypted_file)],
            capture_output=True,
            check=True,
            text=True,
        )
        return cast(dict[str, Any], yaml.safe_load(result.stdout))
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to decrypt {encrypted_file}: {e.stderr}")


def encrypt_file(file_to_encrypt: Path, data: dict[str, Any]) -> None:
    """Encrypt data and save to file.

    Args:
        file_to_encrypt: Name of file to create (e.g., 'proxmox.yaml')
        data: Data to encrypt

    Raises:
        RuntimeError: If encryption fails
    """
    # Write unencrypted data to temp file
    temp_file = file_to_encrypt.with_suffix(".tmp")
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
        temp_file.rename(file_to_encrypt)
    except subprocess.CalledProcessError as e:
        temp_file.unlink(missing_ok=True)
        raise RuntimeError(f"Failed to encrypt {file_to_encrypt}: {e.stderr}")
