"""The ``firmware.update`` resource: keep a QNAP switch on the vendor's latest firmware.

Component layer of ADR-0038. A ``firmware.update`` resource marks the switch whose firmware
follows the vendor's latest release; it has no fields. ``plan`` only reports. The upgrade
runs from ``foundry provider qnap upgrade`` and proves success by polling for the switch
going down and coming back and by re-reading the version, not by the replies of the
install endpoint. The install path is unverified against a real switch.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Protocol

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.provider_instances import SELECTOR_KEYS
from infrafoundry.core.validation import ValidationLevel

from ..client import (
    QnapApiDriftError,
    QnapAuthError,
    QnapError,
    QnapUnreachableError,
)

logger = logging.getLogger(__name__)

FIRMWARE_TYPE = "firmware.update"
FIRMWARE_ADDRESS_PREFIX = "qnap_firmware_update"
POLL_INTERVAL = 5.0
START_GRACE = 60

# Products whose web UI never runs the update check; taken from the vendor's UI bundle.
_NO_UPDATE_CHECK_PRODUCTS = frozenset({"m5216"})
_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
# An entry without ``config:`` is loaded with the whole entry as its config (#1660), so the
# entry-level keys, including the instance selectors, are not fields.
_IGNORED_CONFIG_KEYS = (
    frozenset({"name", "provider", "type", "events", "import_id"}) | SELECTOR_KEYS
)


@dataclass(frozen=True)
class SchemaFinding:
    """One schema finding for a resource."""

    resource: str
    level: ValidationLevel
    message: str


class FirmwareClient(Protocol):
    """What the firmware component needs from the client."""

    def get(self, path: str, *, timeout: float | None = None) -> Any:
        """Return the ``result`` of a GET under ``/api/v1/``."""
        ...

    def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        """Return the ``result`` of a POST under ``/api/v1/``."""
        ...

    def about(self) -> dict[str, Any]:
        """Return ``/api/about``."""
        ...

    def login(self) -> None:
        """Log in once."""
        ...

    def renew(self) -> None:
        """Replace the session token."""
        ...

    def live(self) -> bool:
        """Return True when the switch answers ``/api/live``."""
        ...

    def session(self) -> AbstractContextManager[None]:
        """Log in, yield, log out."""
        ...


class QnapUpgradeError(QnapError):
    """The upgrade did not complete. ``step`` names where it stopped."""

    def __init__(self, step: str, message: str) -> None:
        """Initialize the error.

        Args:
            step: One of ``check``, ``precheck``, ``install``, ``progress``, ``reboot-wait``,
                ``login`` or ``verify``.
            message: What went wrong; never a credential.
        """
        super().__init__(message)
        self.step = step


@dataclass(frozen=True)
class FirmwareInfo:
    """The installed firmware (from ``firmware/info``)."""

    version: str
    build: str | None = None


@dataclass(frozen=True)
class UpdateOffer:
    """The vendor's offer (from ``firmware/update/check``)."""

    newer: bool
    version: str | None = None
    build: str | None = None


@dataclass(frozen=True)
class FirmwareState:
    """What a read-only check found."""

    current: FirmwareInfo
    offer: UpdateOffer | None = None
    skipped_reason: str | None = None


def check_firmware_resources(resources: list[ResourceConfig]) -> list[SchemaFinding]:
    """Check the ``firmware.update`` resources of the environment.

    Args:
        resources: Resources of any type; only ``firmware.update`` is checked.

    Returns:
        Error findings: a bad name, a field (there are none) or more than one resource.
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
            error("the resource has no fields; unknown field(s): " + ", ".join(extra))
        if seen == 2:
            error("only one firmware.update resource is allowed per environment")
    return findings


def _text(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None


def read_firmware(client: FirmwareClient) -> FirmwareInfo:
    """Read the installed firmware from ``firmware/info``.

    Raises:
        QnapApiDriftError: If the reply has no ``version``.
    """
    info = client.get("firmware/info")
    version = _text(info.get("version")) if isinstance(info, dict) else None
    if version is None:
        raise QnapApiDriftError("the switch's 'firmware/info' reply has no 'version'")
    return FirmwareInfo(version, _text(info.get("buildNumber")))


def parse_offer(result: Any) -> UpdateOffer:
    """Interpret a ``firmware/update/check`` result.

    Raises:
        QnapApiDriftError: If ``newer`` is not a bool, or a newer offer has no version.
    """
    if not isinstance(result, dict) or not isinstance(result.get("newer"), bool):
        raise QnapApiDriftError("the switch's 'firmware/update/check' reply has no boolean 'newer'")
    if not result["newer"]:
        return UpdateOffer(False)
    version = _text(result.get("version"))
    if version is None:
        raise QnapApiDriftError("the switch's 'firmware/update/check' offer has no 'version'")
    return UpdateOffer(True, version, _text(result.get("buildNumber")))


def _has_dns_server(client: FirmwareClient) -> bool:
    rows = client.get("dns/server")
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        return False
    val = rows[0].get("val")
    return isinstance(val, dict) and bool(val.get("IpAddress"))


def check_firmware(client: FirmwareClient, check_timeout: float) -> FirmwareState:
    """Read the installed firmware and ask the switch for the vendor's offer.

    The check is skipped, with a reason, when the switch has no DNS server or its product
    is one whose web UI never checks: the UI makes the same decision.

    Args:
        client: A client inside a session.
        check_timeout: Seconds the (slow) update check may take.

    Raises:
        QnapError: If a read fails or a reply has an unexpected shape; a slow check raises
            ``QnapTimeoutError``.
    """
    current = read_firmware(client)
    about = client.about()
    for key in ("Product", "Model"):
        if str(about.get(key, "")).strip().lower() in _NO_UPDATE_CHECK_PRODUCTS:
            return FirmwareState(
                current, skipped_reason="the vendor's web UI never checks this product"
            )
    if not _has_dns_server(client):
        return FirmwareState(
            current,
            skipped_reason=(
                "the switch has no DNS server; it needs DNS and a route to the vendor's "
                "update server"
            ),
        )
    return FirmwareState(
        current, offer=parse_offer(client.get("firmware/update/check", timeout=check_timeout))
    )


def plan_line(resource_name: str, state: FirmwareState, env_name: str) -> tuple[str, bool]:
    """Return the plan line for the resource and whether it is a warning."""
    prefix = f"{FIRMWARE_TYPE} '{resource_name}': "
    if state.skipped_reason is not None:
        return f"{prefix}update check skipped: {state.skipped_reason}", True
    offer = state.offer
    if offer is not None and offer.newer:
        return (
            f"{prefix}{state.current.version} → {offer.version} available "
            f"(run foundry provider qnap upgrade --env {env_name})",
            False,
        )
    return f"{prefix}up to date ({state.current.version})", False


def current_version(client: FirmwareClient) -> str:
    """Describe the switch's firmware for a failure message; best effort, never raises."""
    try:
        return f"firmware {read_firmware(client).version}"
    except (QnapError, OSError):
        return "the switch is unreachable, so its firmware version could not be read"


class QnapFirmwareUpgrader:
    """Installs the offered firmware and waits for the reboot."""

    def __init__(
        self,
        client: FirmwareClient,
        *,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        poll_interval: float = POLL_INTERVAL,
    ) -> None:
        """Initialize the upgrader.

        Args:
            client: A client with a live session.
            sleep: Sleeps between polls; replaced in tests.
            clock: Monotonic clock; replaced in tests.
            poll_interval: Seconds between polls.
        """
        self._client = client
        self._sleep = sleep
        self._clock = clock
        self._poll = poll_interval
        self._relogged = False

    def upgrade(self, expected: str, timeout: int) -> str:
        """Install the firmware the user confirmed and verify it after the reboot.

        There is no second update check: the install acts on the check made moments ago,
        and the post-reboot verification against ``expected`` catches a changed offer.

        Args:
            expected: The version the confirmed check offered.
            timeout: Seconds from the install request until the switch is back.

        Returns:
            The version the switch runs afterwards (equal to ``expected``).

        Raises:
            QnapUpgradeError: On any failure; ``step`` says where.
        """
        deadline = self._clock() + timeout
        self._precheck()
        went_down = self._install_and_watch(deadline)
        missed = self._wait_for_reboot(deadline, went_down, expected)
        return missed if missed is not None else self._login_and_verify(expected)

    def _precheck(self) -> None:
        try:
            condition = self._client.get("firmware/condition")
        except QnapError as exc:
            raise QnapUpgradeError(
                "precheck", f"could not read the firmware condition: {exc}"
            ) from exc
        if isinstance(condition, dict) and condition.get("anomaly") is True:
            detail = condition.get("message")
            raise QnapUpgradeError(
                "precheck",
                "the switch refuses a firmware change"
                + (f": {detail}" if isinstance(detail, str) and detail else ""),
            )

    def _install_and_watch(self, deadline: float) -> bool:
        """Start the install and poll its progress; True when the switch went down."""
        try:
            self._client.renew()
            self._client.post("firmware/update/live", {})
        except QnapUnreachableError:
            return True  # the switch is already going down
        except QnapError as exc:
            raise QnapUpgradeError("install", f"the install request failed: {exc}") from exc
        started = self._clock()
        seen_progress = False
        while True:
            try:
                status = self._client.get("firmware/status")
            except QnapAuthError as exc:
                self._relogin(exc)
                continue
            except QnapUnreachableError:
                return True
            except QnapError as exc:
                raise QnapUpgradeError("progress", f"could not read the progress: {exc}") from exc
            progress = status.get("progress") if isinstance(status, dict) else None
            if not isinstance(progress, str):
                raise QnapUpgradeError("progress", "the progress reply has no 'progress' text")
            if progress == "done":
                return False
            if progress == "failed":
                detail = status.get("message")
                raise QnapUpgradeError(
                    "progress",
                    "the install failed" + (f": {detail}" if isinstance(detail, str) else ""),
                )
            if progress == "none":
                if not seen_progress and self._clock() - started >= START_GRACE:
                    raise QnapUpgradeError("install", "the switch did not start the install")
            else:
                seen_progress = True
                if progress not in ("preparing", "extracting", "installing"):
                    logger.info("unknown firmware progress value %r; continuing", progress)
            if self._clock() >= deadline:
                raise QnapUpgradeError("progress", "timed out waiting for the install to finish")
            self._sleep(self._poll)

    def _relogin(self, cause: Exception) -> None:
        if self._relogged:
            raise QnapUpgradeError(
                "progress", "the session was refused again during the install"
            ) from cause
        self._relogged = True
        try:
            self._client.login()
        except QnapError as exc:
            raise QnapUpgradeError(
                "progress", f"the session expired and a fresh login failed: {exc}"
            ) from exc

    def _wait_for_reboot(self, deadline: float, went_down: bool, expected: str) -> str | None:
        """Wait for down then up; return the version when the reboot was missed but verified."""
        if not went_down:
            while self._client.live():
                if self._clock() >= deadline:
                    return self._verify_missed_reboot(expected)
                self._sleep(self._poll)
        while not self._client.live():
            if self._clock() >= deadline:
                raise QnapUpgradeError(
                    "reboot-wait", "timed out waiting for the switch to come back"
                )
            self._sleep(self._poll)
        return None

    def _verify_missed_reboot(self, expected: str) -> str:
        """The switch was never seen down: succeed only if it already runs ``expected``."""
        try:
            self._client.login()
            installed = read_firmware(self._client).version
        except QnapError as exc:
            raise QnapUpgradeError(
                "login", f"the switch was never seen going down and a login failed: {exc}"
            ) from exc
        if installed != expected:
            raise QnapUpgradeError(
                "reboot-wait", "timed out waiting for the switch to reboot into the new firmware"
            )
        return installed

    def _login_and_verify(self, expected: str) -> str:
        try:
            self._client.login()
        except QnapError as exc:
            raise QnapUpgradeError("login", f"the login after the reboot failed: {exc}") from exc
        try:
            installed = read_firmware(self._client).version
        except QnapError as exc:
            raise QnapUpgradeError(
                "verify", f"could not read the version after the reboot: {exc}"
            ) from exc
        if installed != expected:
            raise QnapUpgradeError(
                "verify",
                f"the switch returned on firmware {installed}; the upgrade did not install "
                f"{expected}",
            )
        return installed


__all__ = [
    "FIRMWARE_ADDRESS_PREFIX",
    "FIRMWARE_TYPE",
    "FirmwareClient",
    "FirmwareInfo",
    "FirmwareState",
    "QnapFirmwareUpgrader",
    "QnapUpgradeError",
    "SchemaFinding",
    "UpdateOffer",
    "check_firmware",
    "check_firmware_resources",
    "current_version",
    "parse_offer",
    "plan_line",
    "read_firmware",
]
