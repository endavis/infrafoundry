"""Shared SOPS decryption utility for YAML files.

Provides a standalone function to load YAML files with automatic SOPS
decryption, used by both ConfigManager and PackageLoader.
"""

import subprocess  # nosec B404 - needed for SOPS decryption
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
