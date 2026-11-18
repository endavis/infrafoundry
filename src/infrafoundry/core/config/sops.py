"""Shared SOPS utilities for YAML files and binary blobs.

Provides standalone functions to load and save YAML files with automatic SOPS
decryption/encryption, used by ConfigManager, PackageLoader, and the config
create command. The binary helpers encrypt and decrypt whole files (such as device
config exports) for the collectors.
"""

import shutil
import subprocess  # nosec B404  # needed for SOPS decryption/encryption
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from infrafoundry.core.config.yaml_loader import load_config_yaml
from infrafoundry.core.exceptions import InfraFoundryError

SopsRun = Callable[..., "subprocess.CompletedProcess[bytes]"]


class SopsError(InfraFoundryError):
    """A SOPS binary operation failed. Never carries file content."""


class SopsCreationRuleError(SopsError):
    """No ``.sops.yaml`` creation rule matches the file being encrypted."""


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
    with open(file_path, encoding="utf-8") as f:
        raw = f.read()

    if "sops:" in raw and "ENC[AES256_GCM," in raw:
        result = subprocess.run(  # trusted sops command
            ["sops", "--decrypt", str(file_path)],
            capture_output=True,
            text=True,
            check=True,
        )
        return load_config_yaml(result.stdout) or {}

    return load_config_yaml(raw) or {}


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
    with open(file_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)

    if encrypt:
        subprocess.run(  # trusted sops command
            ["sops", "--encrypt", "--in-place", str(file_path)],
            capture_output=True,
            text=True,
            check=True,
            cwd=str(config_dir) if config_dir else None,
        )


def _sops_binary() -> str:
    """Return the path of the ``sops`` binary.

    Raises:
        SopsError: If ``sops`` is not on PATH.
    """
    path = shutil.which("sops")
    if path is None:
        raise SopsError("sops binary not found on PATH; install sops to encrypt or decrypt")
    return path


def encrypt_binary(
    plaintext_path: Path,
    final_path: Path,
    *,
    cwd: Path,
    run: SopsRun = subprocess.run,
) -> bytes:
    """Encrypt a file as a SOPS binary document and return the ciphertext.

    ``final_path`` selects the ``.sops.yaml`` creation rule; nothing is written there.

    Args:
        plaintext_path: File holding the plaintext (normally in a temp directory).
        final_path: Where the ciphertext will be stored.
        cwd: Config repo root, used to find ``.sops.yaml``.
        run: Subprocess runner, injectable for tests.

    Raises:
        SopsCreationRuleError: If no creation rule matches ``final_path``.
        SopsError: If sops is missing or fails. The message never has file content.
    """
    argv = [
        _sops_binary(),
        "encrypt",
        "--input-type",
        "binary",
        "--output-type",
        "json",
        "--filename-override",
        str(final_path),
        str(plaintext_path),
    ]
    result = run(argv, capture_output=True, cwd=str(cwd), check=False)  # trusted sops command
    if result.returncode != 0:
        stderr = bytes(result.stderr or b"").decode("utf-8", errors="replace")
        if "no matching creation rules" in stderr.lower():
            raise SopsCreationRuleError(
                f"no .sops.yaml creation rule matches {final_path}; add a path_regex rule for it"
            )
        raise SopsError(f"sops encrypt failed for {final_path} (exit {result.returncode})")
    return bytes(result.stdout)


def decrypt_binary(
    path: Path,
    *,
    cwd: Path,
    run: SopsRun = subprocess.run,
) -> bytes:
    """Decrypt a SOPS binary document (JSON form) and return the plaintext bytes.

    Args:
        path: The encrypted file.
        cwd: Config repo root.
        run: Subprocess runner, injectable for tests.

    Raises:
        SopsError: If sops is missing or fails. The message never has file content.
    """
    argv = [
        _sops_binary(),
        "decrypt",
        "--input-type",
        "json",
        "--output-type",
        "binary",
        str(path),
    ]
    result = run(argv, capture_output=True, cwd=str(cwd), check=False)  # trusted sops command
    if result.returncode != 0:
        raise SopsError(f"sops decrypt failed for {path} (exit {result.returncode})")
    return bytes(result.stdout)
