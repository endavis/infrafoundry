"""Shared SOPS utilities for YAML files.

Provides standalone functions to load and save YAML files with automatic SOPS
decryption/encryption, used by ConfigManager, PackageLoader, and the config
create command.
"""

import subprocess  # nosec B404 - needed for SOPS decryption/encryption
from pathlib import Path
from typing import Any

import yaml


def load_yaml_with_sops(file_path: Path) -> dict[str, Any]:
    """Load a YAML file, decrypting with SOPS if encrypted.

    Detects SOPS encryption by checking for the ``sops`` metadata key
    and ``ENC[AES256_GCM,`` markers in the file content. If found,
    runs ``sops --decrypt`` to get plaintext YAML before parsing.

    Args:
        file_path: Path to the YAML file.

    Returns:
        Parsed YAML data as a dictionary.
    """
    with open(file_path) as f:
        raw = f.read()

    if "sops:" in raw and "ENC[AES256_GCM," in raw:
        result = subprocess.run(  # nosec B603 B607 - trusted sops command
            ["sops", "--decrypt", str(file_path)],
            capture_output=True,
            text=True,
            check=True,
        )
        return yaml.safe_load(result.stdout) or {}

    return yaml.safe_load(raw) or {}


def save_yaml_with_sops(
    file_path: Path,
    data: dict[str, Any],
    *,
    encrypt: bool = False,
    config_dir: Path | None = None,
) -> None:
    """Write YAML data to a file, optionally re-encrypting with SOPS.

    Writes ``data`` as YAML to ``file_path``. When ``encrypt`` is True,
    runs ``sops --encrypt --in-place`` to re-encrypt the file using the
    ``.sops.yaml`` rules discovered from ``config_dir``.

    Args:
        file_path: Path to write the YAML file.
        data: Dictionary to serialize as YAML.
        encrypt: Whether to encrypt the file with SOPS after writing.
        config_dir: Config repo root used as cwd for .sops.yaml discovery.

    Raises:
        subprocess.CalledProcessError: If SOPS encryption fails.
    """
    with open(file_path, "w") as f:
        yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)

    if encrypt:
        subprocess.run(  # nosec B603 B607 - trusted sops command
            ["sops", "--encrypt", "--in-place", str(file_path)],
            capture_output=True,
            text=True,
            check=True,
            cwd=str(config_dir) if config_dir else None,
        )
