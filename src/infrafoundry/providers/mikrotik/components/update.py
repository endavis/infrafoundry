"""The ``system.package.update`` resource: keep RouterOS at the latest release of a channel.

Component layer of ADR-0037. A ``system.package.update`` resource marks the device whose
RouterOS follows the latest release of a channel (``stable`` by default); it has no other
field. ``plan`` only reports. The upgrade runs from ``foundry provider mikrotik upgrade``
in two stages, each ending in a reboot: the RouterOS packages, then the RouterBOARD
firmware (bootloader) when it lags. Success is proven by polling for the device going
down and coming back and by re-reading the versions, not by the replies of the write
endpoints, whose shapes are unverified.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any, Protocol

from infrafoundry.core.exceptions import InfraFoundryError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.provider_instances import SELECTOR_KEYS
from infrafoundry.core.validation import ValidationLevel

from ..client import RouterOSAPIError, RouterOSConnectionError
from ..schema import SchemaFinding

logger = logging.getLogger(__name__)

UPDATE_TYPE = "system.package.update"
UPDATE_ADDRESS_PREFIX = "mikrotik_system_package_update"
CHANNELS = ("stable", "long-term", "testing", "development")
DEFAULT_CHANNEL = "stable"

_UPDATE_PATH = "system/package/update"
_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
# An entry without ``config:`` is loaded with the whole entry as its config (#1660), so the
# entry-level keys, including the instance selectors, are not fields.
_IGNORED_CONFIG_KEYS = (
    frozenset({"name", "provider", "type", "events", "import_id"}) | SELECTOR_KEYS
)
_ABSENT_STATUSES = (400, 404)
_UPTIME_PART = re.compile(r"(\d+)([wdhms])")
_UPTIME_SECONDS = {"w": 604800, "d": 86400, "h": 3600, "m": 60, "s": 1}


class RouterOSUpdateCheckError(InfraFoundryError):
    """The device's update check failed or its reply could not be read."""


class RouterOSUpgradeError(InfraFoundryError):
    """The upgrade did not complete. ``step`` names where it stopped."""

    def __init__(self, step: str, message: str) -> None:
        """Initialize the error.

        Args:
            step: One of ``check``, ``install``, ``reboot-wait``, ``verify-routeros``,
                ``routerboard-upgrade``, ``reboot`` or ``verify-routerboard``.
            message: What went wrong; never a credential or serial number.
        """
        super().__init__(message)
        self.step = step


class UpdateClient(Protocol):
    """What the update component needs from the REST client."""

    def get(self, path: str) -> list[dict[str, str]]:
        """Return the rows under a REST path."""
        ...

    def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        """Call an action endpoint and return the decoded reply."""
        ...


@dataclass(frozen=True)
class UpdateStatus:
    """The device's ``system/package/update`` state."""

    installed_version: str
    latest_version: str | None
    status: str | None
    channel: str | None

    @property
    def update_available(self) -> bool:
        """True when the check found a release newer than the installed one."""
        status = (self.status or "").lower()
        if "new version is available" in status:
            return True
        if "up to date" in status:
            return False
        return bool(self.latest_version) and self.latest_version != self.installed_version


@dataclass(frozen=True)
class RouterBoardStatus:
    """The device's RouterBOARD firmware state (``serial-number`` is never copied)."""

    present: bool
    current_firmware: str | None = None
    upgrade_firmware: str | None = None

    @property
    def lags(self) -> bool:
        """True when the firmware is older than the one the installed RouterOS carries."""
        return (
            self.present
            and bool(self.current_firmware)
            and bool(self.upgrade_firmware)
            and self.current_firmware != self.upgrade_firmware
        )


@dataclass(frozen=True)
class DeviceUpdateState:
    """What a read-only check found."""

    update: UpdateStatus
    routerboard: RouterBoardStatus
    channel_mismatch: tuple[str, str] | None = None
    """``(device channel, declared channel)`` when they differ; no update check was made."""


@dataclass(frozen=True)
class UpgradeReport:
    """What :meth:`RouterOSUpgrader.upgrade` did."""

    routeros_version: str | None = None
    firmware_version: str | None = None
    routerboard_skipped: str | None = None


def declared_channel(resource: ResourceConfig) -> str:
    """Return the channel a ``system.package.update`` resource declares."""
    value = (resource.config or {}).get("channel")
    return str(value) if value else DEFAULT_CHANNEL


def check_update_resources(resources: list[ResourceConfig]) -> list[SchemaFinding]:
    """Check the ``system.package.update`` resources of the environment.

    Args:
        resources: Resources of any type; only ``system.package.update`` is checked.

    Returns:
        Error findings: a bad name, an unknown field, a bad channel or more than one.
    """
    findings: list[SchemaFinding] = []
    seen = 0
    for resource in resources:
        if resource.type != UPDATE_TYPE:
            continue
        seen += 1

        def error(message: str, resource: ResourceConfig = resource) -> None:
            findings.append(
                SchemaFinding(
                    resource.name,
                    ValidationLevel.ERROR,
                    f"{UPDATE_TYPE} '{resource.name}': {message}",
                )
            )

        config = resource.config or {}
        if not _NAME_RE.match(resource.name):
            error("the resource name may use only letters, digits, '_', '.' and '-'")
        extra = sorted(k for k in config if k not in _IGNORED_CONFIG_KEYS and k != "channel")
        if extra:
            error("the only field is 'channel'; unknown field(s): " + ", ".join(extra))
        if config.get("channel") not in (None, "") and config.get("channel") not in CHANNELS:
            error("'channel' must be one of " + ", ".join(CHANNELS))
        if seen == 2:
            error("only one system.package.update resource is allowed per environment")
    return findings


def _first_row(rows: list[dict[str, str]], what: str) -> dict[str, str]:
    if not rows or not isinstance(rows[0], dict):
        raise RouterOSUpdateCheckError(f"{what} returned no data")
    return rows[0]


def _text(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None


def parse_update(row: dict[str, Any]) -> UpdateStatus:
    """Interpret a ``GET system/package/update`` row.

    Raises:
        RouterOSUpdateCheckError: If the row has no ``installed-version``.
    """
    installed = _text(row.get("installed-version"))
    if installed is None:
        raise RouterOSUpdateCheckError("system/package/update has no 'installed-version'")
    return UpdateStatus(
        installed_version=installed,
        latest_version=_text(row.get("latest-version")),
        status=_text(row.get("status")),
        channel=_text(row.get("channel")),
    )


def _failed_status(status: str | None) -> bool:
    lowered = (status or "").lower()
    return "error" in lowered or "failed" in lowered


def parse_check_reply(reply: Any) -> dict[str, Any] | None:
    """Return the section of a ``check-for-updates`` reply that carries the result.

    The reply is a list of progress sections; the last one with ``latest-version`` is the
    result.

    Returns:
        That section, or ``None`` when no section has ``latest-version`` (the caller then
        reads ``system/package/update``).

    Raises:
        RouterOSUpdateCheckError: If the last status reports an error.
    """
    raw: list[Any] = (
        [reply] if isinstance(reply, dict) else reply if isinstance(reply, list) else []
    )
    sections: list[dict[str, Any]] = [s for s in raw if isinstance(s, dict)]
    if sections and _failed_status(_text(sections[-1].get("status"))):
        raise RouterOSUpdateCheckError(f"the update check failed: {sections[-1].get('status')}")
    return next((s for s in reversed(sections) if s.get("latest-version")), None)


def parse_routerboard(row: dict[str, Any]) -> RouterBoardStatus:
    """Interpret a ``GET system/routerboard`` row; never copies the serial number."""
    flag = str(row.get("routerboard", "")).lower() in ("true", "yes")
    current = _text(row.get("current-firmware"))
    target = _text(row.get("upgrade-firmware"))
    if not (flag and current and target):
        return RouterBoardStatus(present=False)
    return RouterBoardStatus(present=True, current_firmware=current, upgrade_firmware=target)


def read_routerboard(client: UpdateClient) -> RouterBoardStatus:
    """Read the RouterBOARD firmware state; absent on a device without it (CHR).

    Raises:
        RouterOSConnectionError: If the device cannot be reached.
        RouterOSAPIError: On an API error other than 400 or 404.
    """
    try:
        rows = client.get("system/routerboard")
    except RouterOSAPIError as exc:
        if exc.status_code in _ABSENT_STATUSES:
            return RouterBoardStatus(present=False)
        raise
    if not rows or not isinstance(rows[0], dict):
        return RouterBoardStatus(present=False)
    return parse_routerboard(rows[0])


def _read_update(client: UpdateClient) -> UpdateStatus:
    return parse_update(_first_row(client.get(_UPDATE_PATH), _UPDATE_PATH))


def _check_now(client: UpdateClient, current: UpdateStatus) -> UpdateStatus:
    """Ask the vendor's server for the latest release on the device's channel."""
    reply = client.post(f"{_UPDATE_PATH}/check-for-updates", {})
    section = parse_check_reply(reply)
    if section is None:
        refreshed = _read_update(client)
        if _failed_status(refreshed.status):
            raise RouterOSUpdateCheckError(f"the update check failed: {refreshed.status}")
        return refreshed
    return replace(
        current,
        latest_version=_text(section.get("latest-version")),
        status=_text(section.get("status")),
    )


def check_update(client: UpdateClient, channel: str | None = None) -> DeviceUpdateState:
    """Check read-only whether the declared channel offers a newer release.

    RouterOS checks the channel set on the device, so when it differs from ``channel``
    no ``check-for-updates`` call is made; the state carries the mismatch instead.

    Args:
        client: REST client.
        channel: The declared channel, or ``None`` to accept the device's.
    """
    update = _read_update(client)
    mismatch = (update.channel or "", channel) if channel and update.channel != channel else None
    if mismatch is None:
        update = _check_now(client, update)
    return DeviceUpdateState(update, read_routerboard(client), mismatch)


def set_channel(client: UpdateClient, channel: str) -> None:
    """Switch the device's update channel. This writes; call it only after confirmation."""
    client.post(f"{_UPDATE_PATH}/set", {"channel": channel})


def plan_line(resource_name: str, state: DeviceUpdateState, env_name: str) -> tuple[str, bool]:
    """Return the plan line for the resource and whether it is a warning."""
    prefix = f"{UPDATE_TYPE} '{resource_name}': "
    hint = f"run foundry provider mikrotik upgrade --env {env_name}"
    if state.channel_mismatch is not None:
        device, declared = state.channel_mismatch
        return (
            f"{prefix}device follows '{device}', resource declares '{declared}'; "
            f"the upgrade command switches it ({hint})",
            True,
        )
    update = state.update
    if update.update_available:
        text = f"{update.installed_version} → {update.latest_version} available"
    else:
        text = f"up to date ({update.installed_version})"
    rb = state.routerboard
    if rb.lags:
        text += f"; RouterBOARD firmware {rb.current_firmware} → {rb.upgrade_firmware} pending"
    if update.update_available or rb.lags:
        text += f" ({hint})"
    return prefix + text, False


def uptime_seconds(text: Any) -> int | None:
    """Parse a RouterOS uptime such as ``1w2d3h4m5s``; ``None`` when unreadable."""
    parts = _UPTIME_PART.findall(str(text or ""))
    if not parts:
        return None
    return sum(int(n) * _UPTIME_SECONDS[unit] for n, unit in parts)


def current_versions(client: UpdateClient) -> str:
    """Describe the device's versions for a failure message; best effort, never raises."""
    try:
        installed = _read_update(client).installed_version
        rb = read_routerboard(client)
    except (InfraFoundryError, OSError):
        return "the device is unreachable, so its versions could not be read"
    text = f"RouterOS {installed}"
    if rb.present:
        text += f", RouterBOARD firmware {rb.current_firmware}"
    return text


class RouterOSUpgrader:
    """Runs the RouterOS and RouterBOARD stages and waits for each reboot."""

    def __init__(
        self,
        client: UpdateClient,
        *,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        poll_interval: float = 5.0,
    ) -> None:
        """Initialize the upgrader.

        Args:
            client: REST client for the device.
            sleep: Sleeps between polls; replaced in tests.
            clock: Monotonic clock; replaced in tests.
            poll_interval: Seconds between polls.
        """
        self._client = client
        self._sleep = sleep
        self._clock = clock
        self._poll = poll_interval

    def upgrade(self, expected_routeros: str | None, timeout: int) -> UpgradeReport:
        """Install ``expected_routeros`` when given, then upgrade lagging RouterBOARD firmware.

        Args:
            expected_routeros: The release the user confirmed; ``None`` skips stage 1.
            timeout: Seconds each stage may take from its request until the device is
                back (there are two reboots, so two deadlines).

        Raises:
            RouterOSUpgradeError: On any failure; ``step`` says where.
        """
        installed: str | None = None
        if expected_routeros is not None:
            self._install(expected_routeros, timeout)
            installed = expected_routeros
        firmware, skipped = self._upgrade_routerboard(timeout)
        return UpgradeReport(installed, firmware, skipped)

    def _uptime(self) -> int | None:
        try:
            rows = self._client.get("system/resource")
        except (RouterOSAPIError, RouterOSConnectionError):
            return None
        return uptime_seconds(rows[0].get("uptime")) if rows else None

    def _install(self, expected: str, timeout: int) -> None:
        deadline = self._clock() + timeout
        try:
            offer = _check_now(self._client, _read_update(self._client))
        except InfraFoundryError as exc:
            raise RouterOSUpgradeError("check", f"the update check failed: {exc}") from exc
        if not offer.update_available or offer.latest_version != expected:
            raise RouterOSUpgradeError(
                "check", "the offer changed since the confirmation; rerun the command"
            )
        baseline = self._uptime()
        down = False
        try:
            self._client.post(f"{_UPDATE_PATH}/install", {})
        except RouterOSConnectionError:
            down = True  # the device is already going down
        except RouterOSAPIError as exc:
            raise RouterOSUpgradeError("install", f"the install request failed: {exc}") from exc
        self._wait_for_reboot(deadline, baseline, down, "reboot-wait", watch_update=True)
        try:
            installed = _read_update(self._client).installed_version
        except InfraFoundryError as exc:
            raise RouterOSUpgradeError(
                "verify-routeros", f"could not read the version after the reboot: {exc}"
            ) from exc
        if installed != expected:
            raise RouterOSUpgradeError(
                "verify-routeros",
                f"the device returned on {installed}; the upgrade did not install {expected}",
            )

    def _upgrade_routerboard(self, timeout: int) -> tuple[str | None, str | None]:
        try:
            before = read_routerboard(self._client)
        except InfraFoundryError as exc:
            raise RouterOSUpgradeError(
                "routerboard-upgrade", f"could not read the RouterBOARD firmware: {exc}"
            ) from exc
        if not before.present:
            logger.info("RouterBOARD firmware stage skipped: the device has no RouterBOARD")
            return None, "no RouterBOARD firmware on this device"
        if not before.lags:
            return None, None
        target = str(before.upgrade_firmware)
        deadline = self._clock() + timeout
        try:
            self._client.post("system/routerboard/upgrade", {})
        except InfraFoundryError as exc:
            raise RouterOSUpgradeError(
                "routerboard-upgrade", f"the firmware upgrade request failed: {exc}"
            ) from exc
        baseline = self._uptime()
        down = False
        try:
            self._client.post("system/reboot", {})
        except RouterOSConnectionError:
            down = True
        except RouterOSAPIError as exc:
            raise RouterOSUpgradeError("reboot", f"the reboot request failed: {exc}") from exc
        self._wait_for_reboot(deadline, baseline, down, "reboot", watch_update=False)
        try:
            after = read_routerboard(self._client)
        except InfraFoundryError as exc:
            raise RouterOSUpgradeError(
                "verify-routerboard", f"could not read the firmware after the reboot: {exc}"
            ) from exc
        if after.current_firmware != target:
            raise RouterOSUpgradeError(
                "verify-routerboard",
                f"the device returned on firmware {after.current_firmware}; expected {target}",
            )
        return target, None

    def _wait_for_reboot(
        self,
        deadline: float,
        baseline: int | None,
        already_down: bool,
        step: str,
        *,
        watch_update: bool,
    ) -> None:
        """Wait until the device went down and came back (or its uptime reset)."""
        if not already_down and self._wait_for_down(deadline, baseline, step, watch_update):
            return  # the uptime reset proves a reboot that was missed; the device is up
        self._wait_for_up(deadline, step)

    def _wait_for_down(
        self, deadline: float, baseline: int | None, step: str, watch_update: bool
    ) -> bool:
        """Poll until unreachable (False) or until the uptime reset (True)."""
        while True:
            try:
                rows = self._client.get("system/resource")
                uptime = uptime_seconds(rows[0].get("uptime")) if rows else None
                if baseline is not None and uptime is not None and uptime < baseline:
                    return True
                if watch_update:
                    status = _read_update(self._client).status
                    if _failed_status(status):
                        raise RouterOSUpgradeError("install", f"the install failed: {status}")
            except RouterOSConnectionError:
                return False
            except RouterOSAPIError as exc:
                logger.debug("poll while waiting for the reboot: %s", exc)
            except RouterOSUpdateCheckError as exc:
                logger.debug("update status unreadable while waiting: %s", exc)
            if self._clock() >= deadline:
                raise RouterOSUpgradeError(step, "timed out waiting for the device to reboot")
            self._sleep(self._poll)

    def _wait_for_up(self, deadline: float, step: str) -> None:
        while True:
            try:
                self._client.get("system/resource")
            except (RouterOSConnectionError, RouterOSAPIError):
                if self._clock() >= deadline:
                    raise RouterOSUpgradeError(
                        step, "timed out waiting for the device to come back"
                    ) from None
                self._sleep(self._poll)
                continue
            return


__all__ = [
    "CHANNELS",
    "DEFAULT_CHANNEL",
    "UPDATE_ADDRESS_PREFIX",
    "UPDATE_TYPE",
    "DeviceUpdateState",
    "RouterBoardStatus",
    "RouterOSUpdateCheckError",
    "RouterOSUpgradeError",
    "RouterOSUpgrader",
    "UpdateClient",
    "UpdateStatus",
    "UpgradeReport",
    "check_update",
    "check_update_resources",
    "current_versions",
    "declared_channel",
    "parse_check_reply",
    "parse_routerboard",
    "parse_update",
    "plan_line",
    "read_routerboard",
    "set_channel",
    "uptime_seconds",
]
