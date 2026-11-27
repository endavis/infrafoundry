"""Atomic writes into SOPS-encrypted ``secrets.yaml`` files.

The file is copied, ``sops set --value-stdin`` changes the copy, and ``os.replace`` swaps it
in. The value goes to sops on stdin, so no key is ever on a command line or in a plaintext
file, and a crash leaves either the old file or the new one.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess  # nosec B404  # runs sops with list args
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from infrafoundry.core.certs.models import CertificateStoreError
from infrafoundry.core.exceptions import SecretError
from infrafoundry.core.ssh_host_key_store import ensure_secrets_file

Run = Callable[..., "subprocess.CompletedProcess[Any]"]

_KEY_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_TIMEOUT_SECONDS = 60
TEMP_MARK = ".infrafoundry-new"


def temp_path(path: Path) -> Path:
    """Return the sibling copy ``sops set`` edits; it keeps the extension so sops reads YAML."""
    return path.with_name(path.stem + TEMP_MARK + path.suffix)


class SecretsWriter:
    """Writes values into encrypted ``secrets.yaml`` files."""

    def __init__(self, run: Run = subprocess.run) -> None:
        """Initialize the writer.

        Args:
            run: ``subprocess.run`` or a stand-in.
        """
        self._run = run

    def ensure_file(self, path: Path, cwd: Path, initial: str) -> None:
        """Create the encrypted file when it is missing.

        Args:
            path: The ``secrets.yaml`` path.
            cwd: Config repo root, where ``.sops.yaml`` is found.
            initial: Plaintext YAML the new file starts with.

        Raises:
            CertificateStoreError: If sops fails.
        """
        try:
            ensure_secrets_file(path, cwd, self._run, initial)
        except SecretError as exc:
            raise CertificateStoreError(str(exc)) from None

    def write_value(self, path: Path, keys: Sequence[str], value: dict[str, Any]) -> None:
        """Set ``keys`` to ``value`` in the encrypted file, atomically.

        Args:
            path: The encrypted ``secrets.yaml``; it must exist.
            keys: The key path, for example ``("variables", "acme_certificates", "proxy")``.
            value: The mapping to store.

        Raises:
            CertificateStoreError: If a key is not a plain identifier, the file is missing, or
                sops fails. The message never carries the value.
        """
        if not keys or not all(_KEY_RE.fullmatch(k) for k in keys):
            raise CertificateStoreError(
                "a secrets key may only hold letters, digits, '_', '-', '.'"
            )
        if not path.exists():
            raise CertificateStoreError(f"{path.name} does not exist")
        index = "".join(f'["{k}"]' for k in keys)
        temp = temp_path(path)
        try:
            shutil.copy2(path, temp)
            result = self._run(
                ["sops", "set", "--value-stdin", str(temp), index],
                input=json.dumps(value),
                capture_output=True,
                text=True,
                timeout=_TIMEOUT_SECONDS,
                check=False,
            )
            if result.returncode != 0:
                detail = (result.stderr or "").strip().splitlines()
                raise CertificateStoreError(
                    f"sops failed to write {path.name} (exit {result.returncode})"
                    + (f": {detail[-1]}" if detail else "")
                )
            os.replace(temp, path)
        except subprocess.TimeoutExpired:
            raise CertificateStoreError(f"sops timed out writing {path.name}") from None
        except OSError as exc:
            raise CertificateStoreError(
                f"could not write {path.name}: {exc.strerror or exc.__class__.__name__}"
            ) from None
        finally:
            temp.unlink(missing_ok=True)
