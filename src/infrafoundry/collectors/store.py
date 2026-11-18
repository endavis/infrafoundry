"""Artifact store: writes collector output into the config repo.

Secret-bearing artifacts are SOPS-encrypted whole-file. The plaintext only exists in a
temporary directory that is removed on every path. Change detection compares SHA-256 of
the plaintexts (the previous file is decrypted in memory), so unchanged artifacts are
not rewritten.
"""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from infrafoundry.core.config import sops

from .base import Artifact, CollectorError

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class Encryptor(Protocol):
    """Encrypts and decrypts whole files."""

    def encrypt(self, plaintext_path: Path, final_path: Path) -> bytes:
        """Return ciphertext for ``plaintext_path`` destined for ``final_path``."""
        ...

    def decrypt(self, path: Path) -> bytes:
        """Return the plaintext of an encrypted file."""
        ...


class SopsEncryptor:
    """Encryptor backed by the SOPS binary helpers."""

    def __init__(self, cwd: Path) -> None:
        """Initialize with the config repo root (where ``.sops.yaml`` lives)."""
        self._cwd = cwd

    def encrypt(self, plaintext_path: Path, final_path: Path) -> bytes:
        """Encrypt with SOPS."""
        return sops.encrypt_binary(plaintext_path, final_path, cwd=self._cwd)

    def decrypt(self, path: Path) -> bytes:
        """Decrypt with SOPS."""
        return sops.decrypt_binary(path, cwd=self._cwd)


@dataclass(frozen=True)
class ArtifactChange:
    """The outcome of storing one artifact."""

    device: str
    path: Path
    status: str


def _write_atomic(path: Path, data: bytes, mode: int) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.unlink(missing_ok=True)
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


class ArtifactStore:
    """Writes a device's artifacts under ``output_dir/<device>/``."""

    def __init__(self, output_dir: Path, encryptor: Encryptor) -> None:
        """Initialize the store.

        Args:
            output_dir: Resolved output directory inside the config repo.
            encryptor: Encrypts secret-bearing artifacts.
        """
        self._root = output_dir.resolve()
        self._encryptor = encryptor

    def store(self, device_name: str, artifacts: list[Artifact]) -> list[ArtifactChange]:
        """Write the artifacts and report what changed.

        Args:
            device_name: Kebab-case device name.
            artifacts: The collector's output.

        Raises:
            CollectorError: If the device name would escape the output directory.
        """
        device_dir = (self._root / device_name).resolve()
        if not _NAME_RE.match(device_name) or device_dir.parent != self._root:
            raise CollectorError(f"invalid device name '{device_name}' for output path")
        device_dir.mkdir(parents=True, exist_ok=True)
        return [self._store_one(device_name, device_dir, a) for a in artifacts]

    def _store_one(self, device: str, device_dir: Path, artifact: Artifact) -> ArtifactChange:
        if artifact.secret_bearing:
            final = device_dir / f"{artifact.name}.sops.json"
            status = self._store_secret(final, artifact)
        else:
            final = device_dir / artifact.name
            status = self._store_plain(final, artifact)
        return ArtifactChange(device, final, status)

    @staticmethod
    def _store_plain(final: Path, artifact: Artifact) -> str:
        if final.exists():
            if artifact.same_as(final.read_bytes()):
                return "unchanged"
            status = "changed"
        else:
            status = "new"
        _write_atomic(final, artifact.content, 0o644)
        return status

    def _store_secret(self, final: Path, artifact: Artifact) -> str:
        status = "new"
        if final.exists():
            try:
                previous = self._encryptor.decrypt(final)
            except Exception:  # unreadable previous export: replace it
                status = "changed (previous unreadable)"
            else:
                if artifact.same_as(previous):
                    return "unchanged"
                status = "changed"
        with tempfile.TemporaryDirectory(prefix="infrafoundry-collect-") as tmp:
            plain = Path(tmp) / artifact.name
            fd = os.open(str(plain), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(artifact.content)
            ciphertext = self._encryptor.encrypt(plain, final)
        _write_atomic(final, ciphertext, 0o600)
        return status
