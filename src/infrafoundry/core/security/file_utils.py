"""Secure file writing utilities for secrets handling."""

import logging
import os
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def secure_write(path: Path, content: str, permissions: int = 0o600) -> None:
    """Write content to a file with restrictive permissions.

    Removes any existing file first, then uses os.open() with explicit
    mode bits to atomically create the file with the correct permissions,
    avoiding the race condition of open() followed by chmod().

    Args:
        path: Path to write to
        content: String content to write
        permissions: File permission bits (default: 0o600 - owner read/write only)
    """
    # Remove existing file so os.open() applies the mode bits on creation
    path.unlink(missing_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, permissions)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
    except BaseException:
        # fd is already closed by os.fdopen, but file may exist
        path.unlink(missing_ok=True)
        raise
    logger.debug("Wrote secure file: %s (mode %s)", path, oct(permissions))


def secure_write_yaml(path: Path, data: dict[str, Any], permissions: int = 0o600) -> None:
    """Write YAML data to a file with restrictive permissions.

    Args:
        path: Path to write to
        data: Dictionary to serialize as YAML
        permissions: File permission bits (default: 0o600 - owner read/write only)
    """
    # Remove existing file so os.open() applies the mode bits on creation
    path.unlink(missing_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, permissions)
    try:
        with os.fdopen(fd, "w") as f:
            yaml.dump(data, f)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    logger.debug("Wrote secure YAML file: %s (mode %s)", path, oct(permissions))
