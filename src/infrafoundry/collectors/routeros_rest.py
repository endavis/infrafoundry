"""Collector for MikroTik RouterOS devices over REST (``/export terse``)."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from infrafoundry.core.config.models import CollectorDeviceConfig
from infrafoundry.core.exceptions import InfraFoundryError
from infrafoundry.providers.mikrotik.client import RouterOSClient
from infrafoundry.providers.mikrotik.settings import MikroTikSettings, settings_from_mapping

from .base import Artifact, CollectorError

_HEADER_RE = re.compile(r"^# .* by RouterOS .*$")


def normalize_export(text: str) -> str:
    """Drop the volatile first-line timestamp comment of a RouterOS export.

    Args:
        text: Raw ``/export`` output.
    """
    lines = text.splitlines(keepends=True)
    if lines and _HEADER_RE.match(lines[0].rstrip("\r\n")):
        lines = lines[1:]
    return "".join(lines)


class RouterOSRestCollector:
    """Reads a RouterOS config export through the existing REST client."""

    def __init__(
        self,
        device: CollectorDeviceConfig,
        client_factory: Callable[[MikroTikSettings], Any] = RouterOSClient,
    ) -> None:
        """Initialize the collector.

        Args:
            device: Resolved device config (``address`` is the REST base URL).
            client_factory: Builds the client from settings; injectable for tests.
        """
        self._device = device
        self._client_factory = client_factory

    def collect(self) -> list[Artifact]:
        """Run ``/export terse`` and return the normalised export.

        Raises:
            CollectorError: If settings or the device call fail.
        """
        try:
            settings = settings_from_mapping(
                {
                    "api_url": self._device.address,
                    "username": self._device.username,
                    "password": self._device.password,
                    "verify_ssl": self._device.verify_ssl,
                    "timeout": self._device.timeout,
                }
            )
            output = str(self._client_factory(settings).execute("/export terse"))
        except InfraFoundryError as exc:
            raise CollectorError(f"{self._device.name}: {exc}") from exc
        return [Artifact("export.rsc", normalize_export(output).encode(), secret_bearing=True)]
