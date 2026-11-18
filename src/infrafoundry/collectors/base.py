"""Collector contracts: artifacts, the collector protocol and the error types."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from infrafoundry.core.config.models import CollectorDeviceConfig
from infrafoundry.core.exceptions import InfraFoundryError


class CollectorError(InfraFoundryError):
    """A collector failed. Messages name devices and keys, never values or content."""


class CollectorAuthError(CollectorError):
    """The device refused the login. Never retried."""


class CollectorConfigError(CollectorError):
    """The ``collectors:`` configuration is missing or invalid."""


class CollectorEncryptionError(CollectorError):
    """A secret-bearing artifact could not be encrypted or decrypted."""


def _identity(content: bytes) -> bytes:
    return content


@dataclass(frozen=True)
class Artifact:
    """One exported file from a device.

    ``compare_key`` maps content to the form used for change detection. The raw
    ``content`` is always what gets stored; the key only masks parts a device
    regenerates on every export (for example re-salted encrypted values), so an
    unchanged device reports no changes.
    """

    name: str
    content: bytes = field(repr=False)
    secret_bearing: bool = False
    compare_key: Callable[[bytes], bytes] = field(default=_identity, repr=False, compare=False)

    def same_as(self, previous: bytes) -> bool:
        """Return True when ``previous`` matches this content under ``compare_key``."""
        new = hashlib.sha256(self.compare_key(self.content)).digest()
        old = hashlib.sha256(self.compare_key(previous)).digest()
        return new == old


class Collector(Protocol):
    """Reads a device's configuration. Implementations never write to the device."""

    def collect(self) -> list[Artifact]:
        """Return the device's exported artifacts."""
        ...


CollectorFactory = Callable[[CollectorDeviceConfig], Collector]
