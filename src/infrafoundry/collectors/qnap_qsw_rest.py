"""Collector for QNAP QSW-M series switches over the web API (ADR-0027, ADR-0038).

One run makes one login, reads a fixed set of configuration endpoints, does one raw GET of
the native ``system/config`` export and always logs out. Every endpoint is stored as one
normalised JSON document. Endpoints this firmware does not serve are listed in
``unavailable.json`` instead of failing the run.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any, Protocol

from infrafoundry.core.config.models import CollectorDeviceConfig
from infrafoundry.providers.qnap.client import (
    QnapApiDriftError,
    QnapApiError,
    QnapClient,
    QnapError,
)
from infrafoundry.providers.qnap.settings import (
    QnapSettings,
    QnapSettingsError,
    settings_from_mapping,
)

from .base import Artifact, CollectorConfigError, CollectorError

logger = logging.getLogger(__name__)

# Configuration endpoints only. Status and statistics endpoints are excluded because they change
# between runs: lacp/info, portlist, ports/statistics, ports/group (per-port packet counters)
# and the */status endpoints.
READ_SET: tuple[str, ...] = (
    "system/info",
    "firmware/info",
    "vlan",
    "vlan/indexs",
    "ports",
    "ports/config",
    "lacp/group",
    "rstp",
    "rstp/priority",
    "rstp/interface",
    "lldp",
    "lldp/interface",
    "qos/mode",
    "qos/default",
    "qos/pcp",
    "qos/dscp",
    "acl/ip",
    "acl/mac",
    "acl/ports",
    "igmp",
    "mirror",
    "loopProtect/config",
    "dns/server",
    "ip/ipv4/interface",
    "ip/ipv4/route",
    "sntp",
    "sntp/server",
    "sntp/timezone",
    "system/web/config",
    "system/https",
    "system/syslog",
    "snmp/community",
    "snmp/security",
    "snmp/address",
    "snmp/trap/event",
    "snmp/service",
    "users",
)
REQUIRED: tuple[str, ...] = ("system/info", "firmware/info", "vlan")
SECRET_ENDPOINTS: frozenset[str] = frozenset(
    {"system/info", "users", "snmp/community", "snmp/security"}
)
NATIVE_EXPORT = "system/config"
NATIVE_EXPORT_NAME = "system-config.bin"
UNAVAILABLE_NAME = "unavailable.json"


class QnapCollectorClient(Protocol):
    """What the collector needs from the QNAP client."""

    def session(self) -> AbstractContextManager[None]:
        """Log in once, yield, and always log out."""
        ...

    def get(self, path: str, *, timeout: float | None = None) -> Any:
        """Return the ``result`` of a GET."""
        ...

    def get_raw(self, path: str, *, timeout: float | None = None) -> bytes:
        """Return the raw body of a GET."""
        ...


def artifact_name(path: str) -> str:
    """Return the file name of an endpoint's document (``ip/ipv4/route`` -> ``ip-ipv4-route.json``).

    Args:
        path: Endpoint path below ``/api/v1/``.
    """
    return path.replace("/", "-") + ".json"


def normalize(result: Any) -> bytes:
    """Serialise a result deterministically (sorted keys, trailing newline).

    Args:
        result: Any JSON-serialisable value.
    """
    return (json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def _reason(exc: QnapError) -> str:
    if isinstance(exc, QnapApiError):
        return f"error {exc.error_code}"
    return "not-json"


class QnapQswRestCollector:
    """Reads the configuration of a QSW-M series switch through the QNAP client."""

    def __init__(
        self,
        device: CollectorDeviceConfig,
        client_factory: Callable[[QnapSettings], QnapCollectorClient] = QnapClient,
    ) -> None:
        """Initialize the collector.

        Args:
            device: Resolved device config (``address`` is the https base URL; the pin is
                ``options.tls_fingerprint``; ``options.native_export: true`` also stores the
                switch's native export, which is not byte-stable and so reads as changed on
                every run).
            client_factory: Builds the client from settings; injectable for tests.
        """
        self._device = device
        self._client_factory = client_factory

    def _settings(self) -> QnapSettings:
        device = self._device
        try:
            return settings_from_mapping(
                {
                    "api_url": device.address,
                    "username": device.username,
                    "password": device.password,
                    "tls_fingerprint": device.options.get("tls_fingerprint"),
                    "verify_ssl": device.verify_ssl,
                    "timeout": device.timeout,
                },
                where=f"collectors device '{device.name}'",
            )
        except QnapSettingsError as exc:
            raise CollectorConfigError(str(exc)) from exc

    def collect(self) -> list[Artifact]:
        """Read the configuration endpoints and the native export.

        Raises:
            CollectorConfigError: If the device settings are invalid.
            CollectorError: If the switch cannot be read or a required endpoint is missing.
        """
        name = self._device.name
        client = self._client_factory(self._settings())
        results: dict[str, Any] = {}
        unavailable: dict[str, str] = {}
        export: bytes | None = None
        try:
            with client.session():
                for path in READ_SET:
                    try:
                        results[path] = client.get(path)
                    except (QnapApiDriftError, QnapApiError) as exc:
                        unavailable[path] = _reason(exc)
                if self._device.options.get("native_export", False) is True:
                    try:
                        export = client.get_raw(NATIVE_EXPORT)
                    except (QnapApiDriftError, QnapApiError) as exc:
                        unavailable[NATIVE_EXPORT] = _reason(exc)
        except QnapError as exc:
            raise CollectorError(f"{name}: {exc}") from exc
        missing = [path for path in REQUIRED if path in unavailable]
        if missing:
            raise CollectorError(
                f"{name}: required endpoint(s) not served: {', '.join(missing)}; "
                "the switch API may have changed"
            )
        logger.info("%s: read %d endpoints, %d unavailable", name, len(results), len(unavailable))
        artifacts = [
            Artifact(
                artifact_name(path),
                normalize(result),
                secret_bearing=path in SECRET_ENDPOINTS,
            )
            for path, result in results.items()
        ]
        if export is not None:
            artifacts.append(Artifact(NATIVE_EXPORT_NAME, export, secret_bearing=True))
        artifacts.append(Artifact(UNAVAILABLE_NAME, normalize(unavailable)))
        return artifacts
