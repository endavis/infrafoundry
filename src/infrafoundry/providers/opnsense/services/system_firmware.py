"""System firmware service for OPNsense direct-API operations (#806).

Manages the OPNsense ``<system><firmware>`` block via the
``firmware/info`` (read) + ``firmware/install/<name>`` (write) endpoints.
This is the **keystone** surface for #806 — without ``firmware.plugins``
automating the install of contrib plugins, the modern controllers for
follow-up issues (#790 AcmeClient) don't exist on
the cutover target and ``infra apply`` for those issues silently
no-ops with 404s.

Identity is the singleton ``settings`` — there is exactly one firmware
configuration per box.

**Apply semantics (per #806 user decision, 2026-05-10):**

- ``apply`` is **install-missing only**: any plugin in YAML but not on
  the box is installed; any plugin on the box but not in YAML is
  **logged at warning level only — never auto-removed**.
- ``destroy`` is a no-op (don't auto-uninstall).

This intentionally violates the usual "live state == YAML state" symmetry
for safety: an operator who forgot to declare ``os-tailscale`` in YAML
should not lose Tailscale on the next apply.

Endpoint surface (26.1; #1149):

- ``GET core/firmware/info`` — plugin/package list (verified live, 26.1.6_2).
- ``GET core/firmware/get`` — settings under ``{"firmware": {...}}``
  (verified live, 26.1.6_2).
- ``POST core/firmware/set`` — settings write (verified live, 26.1.6_2).
- ``POST core/firmware/install/<plugin_name>`` — install one plugin. The
  request reaches OPNsense on 26.1.6_2 but only queues a background job;
  the response acknowledges the request, not the install. A box that is
  out of date refuses it in the job log (#1238).
- ``GET core/firmware/upgradestatus`` — the job's ``status`` (``"running"``
  while it runs) and ``log``. Apply polls it after queuing an install and
  re-reads ``firmware/info``; if the plugin is still not installed once
  the job is no longer running (or on timeout) it raises ``APIError`` with
  the log tail, so apply cannot report success for an install that did not
  happen (#1238).
- ``POST core/firmware/check`` — start a firmware check job (#1452); it
  refreshes the package catalogue and does not change the release.
- ``GET core/firmware/status`` — the cached check result: ``status``
  (``update``/``upgrade``/``none``/``error``), ``upgrade_packages``,
  ``product_id``, ``product_version``, ``status_reboot`` (#1452).
- ``POST core/firmware/update`` — start the minor update (#1452). It takes
  no version argument and reboots the box by itself when needed; apply
  waits on ``upgradestatus`` and re-reads ``firmware/info``. Only with
  ``update: true``. Not yet verified live.
- ``core/firmware/upgrade`` (major) and ``core/firmware/reboot`` are never
  registered or called.
- ``POST core/firmware/remove|lock/<plugin_name>`` — not tested; the apply
  path NEVER calls them.

Field schema:

- ``plugins`` — list of plugin names that should be installed.
- ``update`` — opt-in bool: apply the pending minor firmware update before
  plugin installs (#1452). Never written to the box.
- ``update_timeout`` — seconds the update job plus reboot wait may take
  (default 1800).
- ``mirror``, ``flavour``, ``type``, ``subscription``, ``reboot`` —
  settings fields. Only the keys present in YAML are compared or written,
  so an omitted ``mirror`` is never blanked.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx
from opnsense_openapi import APIResponseError

from infrafoundry.core.exceptions import APIError, AuthenticationError
from infrafoundry.core.provider import ResourceConfig

from ..api_client import OPNsenseClient, SystemClient
from ..components._singleton import diff_singleton
from ._nested_emit import emit_nested_singleton_yaml
from .base import BaseService, raise_on_failed_write

logger = logging.getLogger(__name__)

_INSTALL_TIMEOUT_SECONDS = 300.0
_INSTALL_POLL_INTERVAL_SECONDS = 3.0
_LOG_TAIL_LINES = 20
_URL_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.\-]*://\S+")
_URL_TRAILING = ".,;:)]}'\""
_MASK = "***"

_CHECK_TIMEOUT_SECONDS = 300.0
_CHECK_POLL_INTERVAL_SECONDS = 3.0
_UPDATE_TIMEOUT_SECONDS = 1800
_UPDATE_POLL_INTERVAL_SECONDS = 10.0
_IN_PROGRESS_STATES = ("running", "reboot")

_SETTINGS_FIELDS = ("mirror", "flavour", "type", "subscription", "reboot")


@dataclass(frozen=True)
class PendingUpdate:
    """A minor firmware update the box reports as available (#1452)."""

    from_version: str
    to_version: str
    reboot: bool


class SystemFirmwareService(BaseService):
    """Service for OPNsense system-firmware operations via direct-API.

    Args:
        client: Configured ``OPNsenseClient`` instance.
    """

    def __init__(self, client: OPNsenseClient) -> None:
        """Initialize the firmware service with a SystemClient wrapper."""
        super().__init__(client)
        self.system_client = SystemClient(client)

    # ------------------------------------------------------------------
    # API helpers
    # ------------------------------------------------------------------

    def get_firmware_info(self) -> dict[str, Any]:
        """Fetch firmware/plugin info from OPNsense.

        Returns:
            Raw API response from ``core/firmware/info``.
        """
        return self.system_client.get_firmware_info()

    def get_firmware_settings(self) -> dict[str, Any]:
        """Fetch firmware settings from OPNsense.

        Returns:
            Raw API response from ``core/firmware/get``.
        """
        return self.system_client.get_firmware_settings()

    def set_firmware_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Write firmware settings.

        Args:
            payload: ``{"firmware": {<field>: <value>}}``.

        Returns:
            API response.

        Raises:
            APIError: If OPNsense answers ``{"result": "failed"}``.
        """
        response = self.system_client.set_firmware_settings(payload)
        raise_on_failed_write(response, "set firmware settings")
        return response

    def get_upgrade_status(self) -> dict[str, Any]:
        """Fetch the status of the running or last firmware background job.

        Returns:
            Raw API response from ``core/firmware/upgradestatus``.
        """
        return self.system_client.get_upgrade_status()

    def install_plugin(self, name: str) -> dict[str, Any]:
        """Install a single plugin and wait until it is installed.

        The install endpoint only queues a background job, so this waits
        via :meth:`wait_for_plugin_install` and raises if the plugin is not
        installed afterwards.

        Args:
            name: Plugin name (e.g., ``os-acme-client``).

        Returns:
            API response of the install request.

        Raises:
            APIError: If the request is rejected or the plugin is not
                installed once the job ends or the wait times out.
        """
        response = self.system_client.install_plugin(name)
        raise_on_failed_write(response, f"install firmware plugin {name}")
        self.wait_for_plugin_install(name)
        return response

    def wait_for_plugin_install(
        self,
        name: str,
        *,
        timeout: float = _INSTALL_TIMEOUT_SECONDS,
        interval: float = _INSTALL_POLL_INTERVAL_SECONDS,
    ) -> None:
        """Wait until ``name`` shows as installed in ``firmware/info``.

        Each round re-reads ``firmware/info``; if the plugin is not installed
        it reads ``firmware/upgradestatus``. A ``running`` status keeps the
        wait going. Two consecutive non-running observations (one ``interval``
        apart) with the plugin still missing are a failure; the second
        guards against a stale "done" status left by an earlier job.

        Args:
            name: Plugin name to wait for.
            timeout: Seconds to wait before giving up.
            interval: Seconds between polls.

        Raises:
            APIError: On timeout, or when the job ended without installing
                the plugin. The message carries the tail of the job log.
        """
        deadline = time.monotonic() + timeout
        idle_polls = 0
        while True:
            if name in self.extract_installed_plugins(self.get_firmware_info()):
                return
            status = self.get_upgrade_status()
            running = isinstance(status, dict) and status.get("status") == "running"
            if running:
                idle_polls = 0
            else:
                idle_polls += 1
                if idle_polls >= 2:
                    raise _install_error(
                        name,
                        "the install job ended but the plugin is not installed",
                        status,
                        self._subscription_or_none(),
                    )
            if time.monotonic() >= deadline:
                raise _install_error(
                    name,
                    f"timed out after {timeout:g}s waiting for the install job",
                    status,
                    self._subscription_or_none(),
                )
            time.sleep(interval)

    # ------------------------------------------------------------------
    # Firmware update (#1452)
    # ------------------------------------------------------------------

    def desired_update(self, resource: ResourceConfig) -> tuple[bool, int]:
        """Read ``update`` and ``update_timeout`` from the YAML.

        Args:
            resource: ``system.firmware`` ``ResourceConfig``.

        Returns:
            ``(update_enabled, update_timeout_seconds)``; update is off and the
            timeout 1800 s unless set.
        """
        config = resource.config
        enabled = _is_truthy(config.get("update"))
        raw = config.get("update_timeout")
        timeout = raw if isinstance(raw, int) and not isinstance(raw, bool) and raw > 0 else None
        return enabled, timeout if timeout is not None else _UPDATE_TIMEOUT_SECONDS

    def current_version(self) -> str:
        """Return ``product_version`` from ``core/firmware/info`` (``""`` if absent)."""
        info = self.get_firmware_info()
        return _str(info.get("product_version")) if isinstance(info, dict) else ""

    def check_for_updates(
        self,
        *,
        timeout: float = _CHECK_TIMEOUT_SECONDS,
        interval: float = _CHECK_POLL_INTERVAL_SECONDS,
    ) -> dict[str, Any]:
        """Run a firmware check, wait for the job and return the cached status.

        The check job never changes the release. Like the plugin install wait,
        two consecutive non-running observations end the wait, which guards
        against a stale "done" status left by an earlier job.

        Args:
            timeout: Seconds to wait for the check job.
            interval: Seconds between polls.

        Returns:
            Raw response of ``core/firmware/status``.

        Raises:
            APIError: If the check job does not finish within ``timeout``.
        """
        response = self.system_client.check_firmware()
        raise_on_failed_write(response, "start the firmware check")
        deadline = time.monotonic() + timeout
        idle_polls = 0
        while True:
            status = self.get_upgrade_status()
            if isinstance(status, dict) and status.get("status") == "running":
                idle_polls = 0
            else:
                idle_polls += 1
                if idle_polls >= 2:
                    return self.system_client.get_firmware_status()
            if time.monotonic() >= deadline:
                raise APIError(
                    f"OPNsense firmware check timed out after {timeout:g}s",
                    provider="opnsense",
                )
            time.sleep(interval)

    def status_problem(self, status: Any) -> str | None:
        """Return why a ``firmware/status`` response cannot be trusted, else ``None``.

        ``status == "error"`` carries ``status_msg``; ``none`` without
        ``all_packages`` means no check result is cached yet.
        """
        if not isinstance(status, dict):
            return "firmware status response is not an object"
        state = status.get("status")
        if state == "error":
            msg = _sanitize_log(_str(status.get("status_msg")), self._subscription_or_none())
            return f"firmware check reported an error: {msg or 'no message'}"
        if state == "none" and "all_packages" not in status:
            return "firmware check returned no result (no check data cached)"
        return None

    def pending_update(self, status: dict[str, Any]) -> PendingUpdate | None:
        """Return the pending minor update from a ``firmware/status`` response.

        Only ``status == "update"`` counts; ``upgrade`` (major) and ``none``
        return ``None``. The target version is the ``new_version`` of the
        ``upgrade_packages`` row named ``product_id``, else the current one.

        Args:
            status: Output of ``core/firmware/status``.

        Returns:
            The pending update, or ``None``.
        """
        if not isinstance(status, dict) or status.get("status") != "update":
            return None
        current = _str(status.get("product_version"))
        target = current
        product_id = _str(status.get("product_id"))
        rows = status.get("upgrade_packages")
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict) and product_id and _str(row.get("name")) == product_id:
                    target = _str(row.get("new_version")) or current
                    break
        return PendingUpdate(
            from_version=current,
            to_version=target,
            reboot=_str(status.get("status_reboot")) == "1",
        )

    def start_update(self) -> dict[str, Any]:
        """Start the minor firmware update job.

        Returns:
            API response of the update request.

        Raises:
            APIError: If the request is rejected.
        """
        response = self.system_client.update_firmware()
        raise_on_failed_write(response, "start the firmware update")
        return response

    def wait_for_update(
        self,
        expected: str,
        *,
        timeout: float = _UPDATE_TIMEOUT_SECONDS,
        interval: float = _UPDATE_POLL_INTERVAL_SECONDS,
    ) -> None:
        """Wait until the box runs ``expected``, through any reboot it starts.

        Each round reads ``upgradestatus``. ``running`` and ``reboot`` mean the
        update is in progress, and so do transient transport or API errors
        (the web GUI restarts, the box reboots). Any other status triggers a
        read of ``firmware/info``: the expected ``product_version`` is
        success; otherwise it counts as an idle poll and two in a row are a
        failure (the second guards against a stale "done").

        Args:
            expected: The version the update should reach.
            timeout: Seconds for the job and the reboot wait together.
            interval: Seconds between polls.

        Raises:
            AuthenticationError: If the box rejects the credentials.
            APIError: On timeout, or when the job ended without reaching
                ``expected``. The message carries the sanitised log tail.
        """
        deadline = time.monotonic() + timeout
        idle_polls = 0
        last_log = ""
        while True:
            in_progress = False
            try:
                status = self.get_upgrade_status()
                state = status.get("status") if isinstance(status, dict) else None
                log = status.get("log") if isinstance(status, dict) else None
                if isinstance(log, str) and log.strip():
                    last_log = log
                if state in _IN_PROGRESS_STATES:
                    in_progress = True
                elif self.current_version() == expected:
                    if "Partial update failure" in last_log:
                        logger.warning(
                            "system.firmware: the update reached %s but the firmware log "
                            "reports a partial update failure",
                            expected,
                        )
                    return
            except AuthenticationError:
                raise
            except (httpx.TransportError, APIResponseError, APIError) as exc:
                logger.debug("system.firmware: update poll error %s", type(exc).__name__)
                in_progress = True
            if in_progress:
                idle_polls = 0
            else:
                idle_polls += 1
                if idle_polls >= 2:
                    raise self._update_error(
                        f"the update ended but the box does not run {expected}", last_log
                    )
            if time.monotonic() >= deadline:
                raise self._update_error(
                    f"timed out after {timeout:g}s waiting for {expected}", last_log
                )
            time.sleep(interval)

    def _update_error(self, reason: str, log: str) -> APIError:
        """Build the ``APIError`` for a firmware update that did not complete."""
        return _firmware_log_error(
            f"OPNsense firmware update failed: {reason}", log, self._subscription_or_none()
        )

    def _subscription_or_none(self) -> str | None:
        """Read the configured subscription for log masking; ``None`` on any failure."""
        try:
            fields = self.extract_firmware_settings_fields(self.get_firmware_settings())
        except Exception:  # best effort on an error path; URL masking still applies
            logger.debug("could not read firmware settings to mask the install log")
            return None
        return _str(fields.get("subscription")) or None

    # ------------------------------------------------------------------
    # Field extract / build
    # ------------------------------------------------------------------

    def extract_installed_plugins(self, api_response: dict[str, Any]) -> list[str]:
        """Return the sorted list of plugin names currently installed.

        ``firmware/info`` returns ``plugin: [{name, installed, ...}, ...]``;
        a plugin is installed iff its ``installed`` field equals ``"1"``
        (string sentinel) or ``1`` (int) or any truthy value.

        Args:
            api_response: Raw response from :meth:`get_firmware_info`.

        Returns:
            Sorted list of installed plugin names. Empty list if the
            response shape is unexpected.
        """
        plugin_rows = api_response.get("plugin", [])
        if not isinstance(plugin_rows, list):
            return []
        installed: list[str] = []
        for row in plugin_rows:
            if not isinstance(row, dict):
                continue
            name = _str(row.get("name"))
            if not name:
                continue
            if _is_truthy(row.get("installed")):
                installed.append(name)
        return sorted(installed)

    def build_desired_plugin_list(self, resource: ResourceConfig) -> list[str]:
        """Build the desired plugin list from a YAML singleton.

        Args:
            resource: ``system.firmware`` ``ResourceConfig``.

        Returns:
            Sorted, de-duplicated list of plugin names from
            ``config["plugins"]``. Empty list when no ``plugins`` key.
        """
        config = resource.config
        raw = config.get("plugins", [])
        if isinstance(raw, str):
            names = [s.strip() for s in raw.split(",") if s.strip()]
        elif isinstance(raw, list):
            names = [_str(v) for v in raw if _str(v)]
        else:
            names = []
        return sorted(set(names))

    def extract_firmware_settings_fields(self, api_response: dict[str, Any]) -> dict[str, Any]:
        """Extract firmware settings from a ``core/firmware/get`` response.

        Args:
            api_response: Raw response from :meth:`get_firmware_settings`.

        Returns:
            ``{field: str}`` for every settings field; ``{}`` when the
            ``firmware`` envelope is missing or not a dict. ``plugins`` and
            ``aux`` are ignored.
        """
        envelope = api_response.get("firmware")
        if not isinstance(envelope, dict):
            return {}
        return {field: _str(envelope.get(field)) for field in _SETTINGS_FIELDS}

    def build_desired_firmware_settings_fields(self, resource: ResourceConfig) -> dict[str, Any]:
        """Build the desired settings map: only keys present in YAML.

        Args:
            resource: ``system.firmware`` ``ResourceConfig``.

        Returns:
            ``{field: str}`` for each settings field set in the YAML.
        """
        config = resource.config
        return {field: _str(config[field]) for field in _SETTINGS_FIELDS if field in config}

    def settings_drift(
        self, live: dict[str, Any], desired: dict[str, Any]
    ) -> dict[str, str] | None:
        """Compare only the keys named in YAML.

        Args:
            live: Output of :meth:`extract_firmware_settings_fields`.
            desired: Output of :meth:`build_desired_firmware_settings_fields`.

        Returns:
            The desired keys/values on any difference, else ``None``.
        """
        if not desired:
            return None
        scoped = {key: live.get(key, "") for key in desired}
        return diff_singleton(scoped, desired)

    # ------------------------------------------------------------------
    # Plugin reconciliation
    # ------------------------------------------------------------------

    def desired_vs_installed_plugins(
        self,
        desired: list[str],
        installed: list[str],
    ) -> tuple[list[str], list[str]]:
        """Return ``(install_missing, extras_to_warn)`` plugin name lists.

        - ``install_missing``: in ``desired`` but not in ``installed`` —
          the apply path will install each.
        - ``extras_to_warn``: in ``installed`` but not in ``desired`` —
          **never removed**; the manager logs each at WARNING level so
          the operator can react out-of-band.

        Args:
            desired: Plugin names from YAML.
            installed: Plugin names from the live ``firmware/info`` response.

        Returns:
            Tuple of (sorted install-missing list, sorted extras list).
        """
        desired_set = set(desired)
        installed_set = set(installed)
        return sorted(desired_set - installed_set), sorted(installed_set - desired_set)

    # ------------------------------------------------------------------
    # migrate()
    # ------------------------------------------------------------------

    def export_to_yaml(self) -> str:
        """Export current firmware settings as nested YAML for ``infra migrate``.

        Returns:
            YAML string under the ``opnsense.system.firmware`` namespace.
        """
        info = self.get_firmware_info()
        installed = self.extract_installed_plugins(info)
        settings = self.extract_firmware_settings_fields(self.get_firmware_settings())
        clean: dict[str, Any] = {}
        if installed:
            clean["plugins"] = installed
        for key, value in settings.items():
            if key == "subscription":
                continue
            if isinstance(value, str) and value:
                clean[key] = value
        return emit_nested_singleton_yaml("system.firmware", clean)


def _mask_url(match: re.Match[str]) -> str:
    """Reduce one URL to ``scheme://host``, adding ``/***`` if anything was dropped."""
    raw = match.group(0)
    core = raw.rstrip(_URL_TRAILING)
    trailing = raw[len(core) :]
    try:
        parts = urlsplit(core)
        host = parts.hostname or ""
        port = f":{parts.port}" if parts.port else ""
    except ValueError:
        return f"{_MASK}{trailing}"
    if not host:
        return f"{_MASK}{trailing}"
    if ":" in host:
        host = f"[{host}]"
    dropped = bool(
        parts.path.strip("/") or parts.query or parts.fragment or parts.username or parts.password
    )
    suffix = f"/{_MASK}" if dropped else ""
    return f"{parts.scheme}://{host}{port}{suffix}{trailing}"


def _sanitize_log(text: str, subscription: str | None = None) -> str:
    """Mask the subscription value and strip URLs down to ``scheme://host``.

    OPNsense Business embeds the subscription key as a path segment of the
    mirror URL, which the firmware log can echo.
    """
    if subscription:
        text = text.replace(subscription, _MASK)
    return _URL_RE.sub(_mask_url, text)


def _firmware_log_error(message: str, log: Any, subscription: str | None = None) -> APIError:
    """Build an ``APIError`` carrying the sanitised tail of a firmware job log."""
    tail = ""
    if isinstance(log, str):
        tail = _sanitize_log("\n".join(log.strip().splitlines()[-_LOG_TAIL_LINES:]), subscription)
    detail = f"; firmware log tail:\n{tail}" if tail else "; no firmware log available"
    return APIError(f"{message}{detail}", response=tail or None, provider="opnsense")


def _install_error(
    name: str, reason: str, status: Any, subscription: str | None = None
) -> APIError:
    """Build the ``APIError`` for a plugin install that did not complete."""
    log = status.get("log") if isinstance(status, dict) else None
    return _firmware_log_error(
        f"OPNsense did not install firmware plugin {name}: {reason}", log, subscription
    )


def _is_truthy(value: Any) -> bool:
    """OPNsense returns ``"1"`` / ``"0"`` / int / bool — accept any truthy form."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        return value.strip() not in ("", "0", "false", "False", "no", "No", "off")
    return bool(value)


def _str(value: Any) -> str:
    """Return a stripped string for any scalar."""
    if value is None:
        return ""
    return str(value).strip()
