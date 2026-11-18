"""Run the collectors of an environment and store their artifacts."""

from __future__ import annotations

import logging
import subprocess  # nosec B404  # only for the exception type
from dataclasses import dataclass, field

import requests

from infrafoundry.core.exceptions import InfraFoundryError

from . import COLLECTORS
from .base import CollectorFactory
from .config import ConfigSource, load_collection, resolve_device
from .store import ArtifactChange, ArtifactStore, Encryptor, SopsEncryptor

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeviceResult:
    """Outcome for one device: either changes or an error message."""

    name: str
    changes: list[ArtifactChange] = field(default_factory=list)
    error: str | None = None


@dataclass(frozen=True)
class CollectionReport:
    """Outcomes of one run."""

    results: list[DeviceResult]

    @property
    def changed(self) -> list[ArtifactChange]:
        """Artifacts that are new or changed."""
        return [c for r in self.results for c in r.changes if c.status != "unchanged"]

    @property
    def failed(self) -> list[DeviceResult]:
        """Devices that failed."""
        return [r for r in self.results if r.error]


def collect_environment(
    config_manager: ConfigSource,
    env_name: str,
    devices: tuple[str, ...] = (),
    *,
    registry: dict[str, CollectorFactory] | None = None,
    encryptor: Encryptor | None = None,
) -> CollectionReport:
    """Collect every selected device of an environment; a failing device does not stop others.

    Args:
        config_manager: Config manager of the config repo.
        env_name: Environment name.
        devices: Device names to restrict to; empty means all.
        registry: Collector factories by type (defaults to the built-ins).
        encryptor: Encrypts secret-bearing artifacts (defaults to SOPS).

    Raises:
        CollectorConfigError: If the configuration is unusable as a whole.
    """
    factories = registry if registry is not None else COLLECTORS
    collection = load_collection(config_manager, env_name, devices, frozenset(factories))
    store = ArtifactStore(collection.output_dir, encryptor or SopsEncryptor(collection.config_root))
    results: list[DeviceResult] = []
    for entry in collection.devices:
        try:
            device = resolve_device(collection.env_config, entry)
            artifacts = factories[device.type](device).collect()
            changes = store.store(device.name, artifacts)
        except (InfraFoundryError, requests.RequestException, subprocess.SubprocessError) as exc:
            logger.warning("collect failed for %s (%s)", entry.name, entry.type)
            results.append(DeviceResult(entry.name, error=str(exc)))
            continue
        logger.info(
            "collected %s (%s): %s",
            entry.name,
            entry.type,
            ", ".join(f"{c.path.name}={c.status}" for c in changes),
        )
        results.append(DeviceResult(entry.name, changes))
    return CollectionReport(results)
