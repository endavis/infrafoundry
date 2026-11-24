"""The ``glinet.firmware`` resource: check for, and install, the vendor's latest release.

Component layer of ADR-0036. A ``glinet.firmware`` resource carries no configuration; it
marks a device whose firmware is kept at the vendor's latest release. ``plan`` only
reports; the upgrade runs from ``foundry provider openwrt upgrade`` and uses the
vendor's online upgrade, keeping the configuration and packages.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from infrafoundry.core.exceptions import InfraFoundryError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.provider_instances import SELECTOR_KEYS
from infrafoundry.core.validation import ValidationLevel
from infrafoundry.providers.openwrt.glinet.rpc import (
    GlinetApiDriftError,
    GlinetUnreachableError,
)
from infrafoundry.providers.openwrt.schema import SchemaFinding

logger = logging.getLogger(__name__)

FIRMWARE_TYPE = "glinet.firmware"
FIRMWARE_ADDRESS_PREFIX = "openwrt_glinet_firmware"

STATUS_FAILURES = {
    2: "download failed",
    5: "image verification failed",
    7: "upgrade failed",
    9: "signature verification failed",
}
STATUS_REBOOTING = frozenset({4, 6})
STATUS_DOWNLOADING = 1

_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
# An entry without ``config:`` is loaded with the whole entry as its config (#1660), so the
# entry-level keys, including the instance selectors (``device`` ...), are not fields.
_IGNORED_CONFIG_KEYS = (
    frozenset({"name", "provider", "type", "events", "import_id"}) | SELECTOR_KEYS
)


class FirmwareUpgradeError(InfraFoundryError):
    """The firmware upgrade did not complete."""


class RpcClient(Protocol):
    """What the firmware component needs from the RPC client."""

    def session(self) -> Any:
        """Log in once; a context manager yielding the session id."""
        ...

    def call(self, sid: str, module: str, method: str, params: dict[str, Any] | None = None) -> Any:
        """Call one API method."""
        ...

    def probe_tls(self) -> None:
        """Complete a TLS handshake without sending a request."""
        ...


@dataclass(frozen=True)
class FirmwareStatus:
    """The router's answer to ``check_firmware_online``."""

    current_version: str
    current_type: str | None
    version_new: str | None

    @property
    def update_available(self) -> bool:
        """True when the vendor offers a version."""
        return bool(self.version_new)


def check_firmware_resources(resources: list[ResourceConfig]) -> list[SchemaFinding]:
    """Check the ``glinet.firmware`` resources of one device.

    Args:
        resources: Resources of any type; only ``glinet.firmware`` is checked.

    Returns:
        Error findings: a bad name, any configuration field, or more than one per device.
    """
    findings: list[SchemaFinding] = []
    seen = 0
    for resource in resources:
        if resource.type != FIRMWARE_TYPE:
            continue
        seen += 1

        def error(message: str, resource: ResourceConfig = resource) -> None:
            findings.append(
                SchemaFinding(
                    resource.name,
                    ValidationLevel.ERROR,
                    f"{FIRMWARE_TYPE} '{resource.name}': {message}",
                )
            )

        if not _NAME_RE.match(resource.name):
            error("the resource name may use only letters, digits, '_', '.' and '-'")
        extra = sorted(k for k in (resource.config or {}) if k not in _IGNORED_CONFIG_KEYS)
        if extra:
            error("takes no fields; unknown field(s): " + ", ".join(extra))
        if seen == 2:
            error("only one glinet.firmware resource is allowed per device")
    return findings


def parse_check(result: Any) -> FirmwareStatus:
    """Interpret a ``check_firmware_online`` reply.

    Raises:
        GlinetApiDriftError: If the reply is not an object or has no ``current_version``.
    """
    if not isinstance(result, dict):
        raise GlinetApiDriftError("'check_firmware_online' did not return an object")
    current = result.get("current_version")
    if not isinstance(current, str) or not current:
        raise GlinetApiDriftError("'check_firmware_online' reply has no 'current_version'")
    new = result.get("version_new")
    if new is not None and not isinstance(new, str):
        raise GlinetApiDriftError("'check_firmware_online' reply has a non-text 'version_new'")
    kind = result.get("current_type")
    return FirmwareStatus(
        current_version=current,
        current_type=kind if isinstance(kind, str) else None,
        version_new=new or None,
    )


def check_firmware(client: RpcClient, sid: str | None = None) -> FirmwareStatus:
    """Ask the router whether the vendor offers a newer release.

    Args:
        client: RPC client.
        sid: An open session id; without one the call logs in and out by itself.
    """
    if sid is not None:
        return parse_check(client.call(sid, "upgrade", "check_firmware_online"))
    with client.session() as opened:
        return parse_check(client.call(opened, "upgrade", "check_firmware_online"))


def plan_line(resource_name: str, status: FirmwareStatus, env_name: str) -> str:
    """Return the one-line plan report for a firmware resource."""
    if not status.update_available:
        return f"{FIRMWARE_TYPE} '{resource_name}': up to date ({status.current_version})"
    return (
        f"{FIRMWARE_TYPE} '{resource_name}': {status.current_version} → "
        f"{status.version_new} available (run foundry provider openwrt upgrade --env {env_name})"
    )


class FirmwareUpgrader:
    """Runs the vendor online upgrade for one router and waits for it to come back."""

    def __init__(
        self,
        client: RpcClient,
        *,
        host_key_probe: Callable[[], None],
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        poll_interval: float = 2.0,
        start_grace: float = 60.0,
    ) -> None:
        """Initialize the upgrader.

        Args:
            client: RPC client for the router.
            host_key_probe: Raises when the SSH host key no longer matches the pinned one.
            sleep: Sleeps between polls; replaced in tests.
            clock: Monotonic clock; replaced in tests.
            poll_interval: Seconds between status polls.
            start_grace: Seconds the router may take to start the upgrade.
        """
        self._client = client
        self._host_key_probe = host_key_probe
        self._sleep = sleep
        self._clock = clock
        self._poll = poll_interval
        self._grace = start_grace

    def upgrade(self, expected_new: str, timeout: int) -> FirmwareStatus:
        """Install ``expected_new`` and verify the router reports it afterwards.

        Args:
            expected_new: The version the user confirmed.
            timeout: Seconds from the upgrade request until the router answers again and
                its SSH host key checks out. The post-reboot host-key check retries until
                this deadline, because a router's SSH may be served by another daemon until
                boot finishes; it passes only once the pinned key is presented.

        Returns:
            The router's status after the upgrade.

        Raises:
            FirmwareUpgradeError: On any failure; a rejected offer, a failed status, a
                timeout, a host key still not matching at the deadline or a version that
                did not change.
            GlinetRpcError: On a transport, pin, login or API-shape failure.
        """
        deadline = self._clock() + timeout
        already_down = self._start(expected_new, deadline)
        self._wait_for_down(deadline, already_down)
        self._wait_for_up(deadline)
        self._verify_host_key(deadline)
        status = check_firmware(self._client)
        if status.current_version != expected_new:
            raise FirmwareUpgradeError(
                f"the router returned on {status.current_version}; the upgrade did not install "
                f"{expected_new}"
            )
        return status

    def _start(self, expected_new: str, deadline: float) -> bool:
        """Re-check the offer, request the upgrade and poll until it heads for reboot.

        Returns:
            True once the router is already unreachable (it may be rebooting).
        """
        with self._client.session() as sid:
            offer = check_firmware(self._client, sid)
            if offer.version_new != expected_new:
                raise FirmwareUpgradeError(
                    "the offer changed since the confirmation; rerun the command"
                )
            reply = self._client.call(
                sid, "upgrade", "upgrade_online", {"keep_config": True, "keep_package": True}
            )
            if isinstance(reply, dict) and reply.get("need_reboot_flag"):
                raise FirmwareUpgradeError(
                    "the router asks for a reboot before upgrading (low memory); "
                    "reboot it and rerun the command"
                )
            return self._poll_status(sid, deadline)

    def _poll_status(self, sid: str, deadline: float) -> bool:
        began = self._clock()
        while True:
            try:
                reply = self._client.call(sid, "upgrade", "get_online_upgrade_status")
            except GlinetUnreachableError:
                return True  # accepted, now probably rebooting
            status = reply.get("status") if isinstance(reply, dict) else None
            if isinstance(status, bool) or not isinstance(status, int):
                if self._clock() - began > self._grace:
                    raise FirmwareUpgradeError("the upgrade did not start")
            elif status in STATUS_FAILURES:
                raise FirmwareUpgradeError(f"firmware upgrade {STATUS_FAILURES[status]}")
            elif status in STATUS_REBOOTING:
                return False
            elif status == STATUS_DOWNLOADING:
                percent = reply.get("percent") if isinstance(reply, dict) else None
                logger.info("firmware download in progress (%s%%)", percent)
            else:
                logger.debug("firmware upgrade status %s", status)
            if self._clock() >= deadline:
                raise FirmwareUpgradeError("timed out waiting for the firmware upgrade")
            self._sleep(self._poll)

    def _wait_for_down(self, deadline: float, already_down: bool) -> None:
        if already_down:
            return
        while True:
            try:
                self._client.probe_tls()
            except GlinetUnreachableError:
                return
            if self._clock() >= deadline:
                raise FirmwareUpgradeError("timed out waiting for the router to reboot")
            self._sleep(self._poll)

    def _verify_host_key(self, deadline: float) -> None:
        """Run the host-key probe, retrying until it passes or the deadline is reached."""
        while True:
            try:
                self._host_key_probe()
            except Exception as exc:
                if self._clock() >= deadline:
                    if isinstance(exc, FirmwareUpgradeError):
                        raise
                    raise FirmwareUpgradeError(
                        f"the router's SSH host key could not be verified after the upgrade: {exc}"
                    ) from exc
                logger.debug("host-key check not yet passing (%s); retrying", exc)
                self._sleep(self._poll)
                continue
            return

    def _wait_for_up(self, deadline: float) -> None:
        while True:
            try:
                self._client.probe_tls()
            except GlinetUnreachableError:
                if self._clock() >= deadline:
                    raise FirmwareUpgradeError(
                        "timed out waiting for the router to come back"
                    ) from None
                self._sleep(self._poll)
                continue
            return


__all__ = [
    "FIRMWARE_ADDRESS_PREFIX",
    "FIRMWARE_TYPE",
    "FirmwareStatus",
    "FirmwareUpgradeError",
    "FirmwareUpgrader",
    "check_firmware",
    "check_firmware_resources",
    "parse_check",
    "plan_line",
]
